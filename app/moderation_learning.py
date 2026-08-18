from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.admin_store import AdminStore


SPLIT_MARKER = " <나눔> "
AUTO_RETRAIN_LABELS = 50


def _fragment_seed_data() -> tuple[list[str], list[int]]:
    complete = [
        "아 나도 그란돈 잡고 싶어",
        "저도 오늘 저녁 레이드 갈게요",
        "혹시 내일 같이 하실 분 있나요",
        "지금 접속하면 초대해 드릴게요",
        "이번 이벤트 보너스가 정말 좋네요",
        "뮤츠 레이드 한 자리 남았습니다",
        "오늘 날씨 부스트는 불꽃 타입이에요",
        "친구 코드 보내 주시면 추가할게요",
        "아 진짜 이건 아니지요",
        "저는 블랙큐레무가 더 좋아요",
        "지금 가는 중이라 조금 늦을 것 같아요",
        "가이오가 원시 에너지가 필요합니다",
    ]
    positives: list[str] = []
    for sentence in complete:
        words = sentence.split()
        for cut in range(1, len(words)):
            positives.append(" ".join(words[:cut]) + SPLIT_MARKER + " ".join(words[cut:]))
        if len(words) >= 4:
            positives.append(
                " ".join(words[:1])
                + SPLIT_MARKER
                + " ".join(words[1:3])
                + SPLIT_MARKER
                + " ".join(words[3:])
            )

    independent_pairs = [
        ("안녕하세요", "레이드 하실 분?"),
        ("네", "알겠습니다"),
        ("감사합니다", "좋은 하루 보내세요"),
        ("지금 가는 중임", "오늘은 어려움"),
        ("레이드 끝남", "내일 다시 할게요"),
        ("저도 참가할게요", "친구 코드 부탁드려요"),
        ("오늘 날씨가 좋네요", "산책 다녀오겠습니다"),
        ("피카츄 잡았어요", "개체값도 좋네요"),
        ("네 가능합니다", "몇 시에 시작하나요?"),
        ("확인했습니다", "잠시 후 들어갈게요"),
        ("도감 확인했어요", "정보 감사합니다"),
        ("오늘은 못 갑니다", "다음에 참여할게요"),
    ]
    negatives = [left + SPLIT_MARKER + right for left, right in independent_pairs]
    return positives + negatives, [1] * len(positives) + [0] * len(negatives)


def _eums_seed_data() -> tuple[list[str], list[int]]:
    stems = [
        "레이드 확인",
        "참가 가능",
        "친구 추가",
        "초대 완료",
        "자리 확인",
        "이벤트 확인",
        "포인트 지급",
        "도감 검색",
        "오늘 참석",
        "내일 접속",
        "원시 에너지 필요",
        "모집 마감",
    ]
    positives = [
        *(f"{stem}했음" for stem in stems),
        *(f"{stem}함" for stem in stems),
        *(f"{stem} 중임" for stem in stems),
        "오늘 못 감",
        "레이드 끝남",
        "지금 가는 중임",
        "조금 늦을 예정",
        "현재 자리 없음",
        "내일 다시 할 예정임",
        "초대 받는 중",
        "상관없음",
        "문제없음",
        "그렇게 하면 됨",
        "경고 주지 마셈",
    ]
    negatives = [
        *(f"{stem}했습니다" for stem in stems),
        *(f"{stem}해요" for stem in stems),
        *(f"{stem} 중입니다" for stem in stems),
        "오늘은 못 가요",
        "레이드가 끝났습니다",
        "지금 가는 중이에요",
        "조금 늦을 예정입니다",
        "현재 자리가 없습니다",
        "원시 에너지가 필요합니다",
        "좋은 마음",
        "처음 뵙겠습니다",
        "도움 주셔서 감사합니다",
        "구름이 많아요",
        "이름이 무엇인가요",
        "포켓몬을 잡았습니다",
        "안녕하세요",
    ]
    return positives + negatives, [1] * len(positives) + [0] * len(negatives)


class ModerationClassifier:
    """현재 활성화된 자체 학습 모델을 지연 로드한다."""

    def __init__(self, store: AdminStore) -> None:
        self.store = store
        self._version = ""
        self._artifact: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._version = ""
            self._artifact = None

    def _load(self) -> dict[str, Any] | None:
        active = self.store.active_moderation_model()
        if not active:
            return None
        version = str(active["version"])
        with self._lock:
            if self._artifact is not None and self._version == version:
                return self._artifact
            path = Path(str(active["artifactPath"]))
            if not path.is_file():
                return None
            import joblib

            artifact = joblib.load(path)
            if not isinstance(artifact, dict):
                return None
            self._artifact = artifact
            self._version = version
            return artifact

    @staticmethod
    def _probability(model: Any, text: str) -> float:
        probabilities = model.predict_proba([text])[0]
        classes = list(model.classes_)
        return float(probabilities[classes.index(1)])

    def predict_fragment(self, messages: tuple[str, ...]) -> tuple[float, bool]:
        artifact = self._load()
        if not artifact or "fragment" not in artifact:
            return 0.0, False
        text = SPLIT_MARKER.join(message.strip() for message in messages if message.strip())
        return self._probability(artifact["fragment"], text), True

    def predict_eums(self, text: str) -> tuple[float, bool]:
        artifact = self._load()
        if not artifact or "eums" not in artifact:
            return 0.0, False
        return self._probability(artifact["eums"], text.strip()), True


class ModerationLearningManager:
    """관리자 판정과 합성 예시로 모델을 만들고 안전하게 교체한다."""

    def __init__(self, store: AdminStore, classifier: ModerationClassifier) -> None:
        self.store = store
        self.classifier = classifier
        self.models_dir = store.db_path.parent / "models"
        self._train_lock = threading.Lock()

    @staticmethod
    def _pipeline():
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        return Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        analyzer="char",
                        ngram_range=(1, 5),
                        min_df=1,
                        max_features=30000,
                        sublinear_tf=True,
                    ),
                ),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        C=2.0,
                        max_iter=500,
                        random_state=3621,
                    ),
                ),
            ]
        )

    @staticmethod
    def _metrics(model: Any, texts: list[str], labels: list[int]) -> dict[str, float]:
        from sklearn.metrics import precision_score, recall_score

        predicted = model.predict(texts)
        precision = float(precision_score(labels, predicted, zero_division=0))
        recall = float(recall_score(labels, predicted, zero_division=0))
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @staticmethod
    def _holdout(texts: list[str], labels: list[int]) -> tuple[list[str], list[int], list[str], list[int]]:
        from sklearn.model_selection import train_test_split

        train_x, test_x, train_y, test_y = train_test_split(
            texts,
            labels,
            test_size=0.25,
            random_state=3621,
            stratify=labels,
        )
        return train_x, train_y, test_x, test_y

    def needs_training(self) -> bool:
        active = self.store.active_moderation_model()
        if active is None:
            return True
        return self.store.reviewed_moderation_count() - int(active["reviewedCount"]) >= AUTO_RETRAIN_LABELS

    def train(self, force: bool = False) -> dict[str, Any]:
        if not force and not self.needs_training():
            return {"trained": False, "reason": "새 판정이 충분히 쌓이지 않았습니다.", **self.status()}
        if not self._train_lock.acquire(blocking=False):
            return {"trained": False, "reason": "이미 학습 중입니다.", **self.status()}
        try:
            fragment_x, fragment_y = _fragment_seed_data()
            eums_x, eums_y = _eums_seed_data()
            fragment_train_x, fragment_train_y, fragment_test_x, fragment_test_y = self._holdout(
                fragment_x, fragment_y
            )
            eums_train_x, eums_train_y, eums_test_x, eums_test_y = self._holdout(eums_x, eums_y)

            reviewed = self.store.moderation_training_examples()
            reviewed_count = self.store.reviewed_moderation_count()
            for item in reviewed:
                label = 1 if item["status"] == "confirmed" else 0
                if item["kind"] == "fragment":
                    fragment_train_x.append(SPLIT_MARKER.join(item["messages"]))
                    fragment_train_y.append(label)
                elif item["kind"] == "eums":
                    eums_train_x.extend(item["messages"])
                    eums_train_y.extend([label] * len(item["messages"]))

            fragment_model = self._pipeline()
            eums_model = self._pipeline()
            fragment_model.fit(fragment_train_x, fragment_train_y)
            eums_model.fit(eums_train_x, eums_train_y)
            metrics = {
                "fragment": self._metrics(fragment_model, fragment_test_x, fragment_test_y),
                "eums": self._metrics(eums_model, eums_test_x, eums_test_y),
            }
            accepted = (
                metrics["fragment"]["precision"] >= 0.8
                and metrics["fragment"]["recall"] >= 0.7
                and metrics["eums"]["precision"] >= 0.8
                and metrics["eums"]["recall"] >= 0.7
            )
            current = self.store.active_moderation_model()
            if accepted and current:
                current_metrics = current.get("metrics") or {}
                for kind in ("fragment", "eums"):
                    previous_f1 = float(
                        (current_metrics.get(kind) or {}).get("f1") or 0.0
                    )
                    if metrics[kind]["f1"] + 0.03 < previous_f1:
                        accepted = False
                        break
            version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            self.models_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = self.models_dir / f"moderation-{version}.joblib"
            import joblib

            joblib.dump(
                {
                    "version": version,
                    "fragment": fragment_model,
                    "eums": eums_model,
                    "metrics": metrics,
                },
                artifact_path,
            )
            self.store.save_moderation_model(
                version=version,
                artifact_path=str(artifact_path.resolve()),
                metrics=metrics,
                reviewed_count=reviewed_count,
                synthetic_count=len(fragment_x) + len(eums_x),
                activate=accepted,
            )
            if accepted:
                self.classifier.invalidate()
            return {"trained": True, "accepted": accepted, "version": version, "metrics": metrics, **self.status()}
        finally:
            self._train_lock.release()

    def rollback(self) -> dict[str, Any]:
        restored = self.store.rollback_moderation_model()
        if not restored:
            return {"ok": False, "reason": "복구할 이전 모델이 없습니다.", **self.status()}
        self.classifier.invalidate()
        return {"ok": True, **self.status()}

    def status(self) -> dict[str, Any]:
        active = self.store.active_moderation_model()
        return {
            "active": active,
            "reviewedCount": self.store.reviewed_moderation_count(),
            "retrainAt": AUTO_RETRAIN_LABELS,
        }
