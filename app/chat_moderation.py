from __future__ import annotations

import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ModerationSignal:
    kind: str
    score: float
    messages: tuple[str, ...]
    features: dict[str, float | int | bool]
    sent_at: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModerationSettings:
    enabled: bool = True
    fragment_count: int = 2
    fragment_window_seconds: int = 12
    eums_count: int = 1


@dataclass(frozen=True)
class _TimedMessage:
    at: datetime
    text: str
    eums: bool


_EUMS_PREFILTER = re.compile(r"(?:음|움|슴|함|임|ㅁ|ᆷ)[.!?~ㅋㅎ\s]*$")
_FALLBACK_EUMS = re.compile(
    r"(?:했|됐|갔|왔|봤|먹었|있|없|맞|끝났|가능|불가능|아니|중|예정|완료|확인|필요)(?:음|슴|함|임)[.!?~ㅋㅎ\s]*$"
)
_TRAILING_NOISE = re.compile(r"[\s.!?~ㅋㅎ]+$")
_SPACE = re.compile(r"\s+")
_COMPLETE_ENDING = re.compile(
    r"(?:[.!?]|요|니다|습니다|죠|네요|세요|이다|한다|했다|된다|됐다|있다|없다)$"
)
_COMPLETE_SHORT_MESSAGES = {
    "네",
    "예",
    "아니요",
    "안녕하세요",
    "감사합니다",
    "알겠습니다",
    "좋아요",
    "맞아요",
}


class KoreanChatAnalyzer:
    """한국어 표현과 전송 간격을 함께 보는 관찰용 분석기.

    분석 결과는 자동 제재에 쓰지 않고 관리자 판정용 사례로만 넘긴다.
    """

    def __init__(self, predictor=None) -> None:
        self._messages: dict[tuple[str, str], deque[_TimedMessage]] = defaultdict(deque)
        self._fragment_runs: dict[str, tuple[str, deque[_TimedMessage]]] = {}
        self._fragment_suppressed_until: dict[str, datetime] = {}
        self._last_signal: dict[tuple[str, str, str], datetime] = {}
        self._lock = threading.Lock()
        self._kiwi = None
        self._kiwi_attempted = False
        self._predictor = predictor

    def warm_up(self) -> bool:
        return self._get_kiwi() is not None

    def suppress_fragments(
        self,
        room: str,
        seconds: int = 15,
        now: datetime | None = None,
    ) -> None:
        """Temporarily stop fragment detection in one room."""
        current = now or datetime.now(timezone.utc)
        until = current + timedelta(seconds=max(1, seconds))
        with self._lock:
            active = self._fragment_runs.pop(room, None)
            if active is not None:
                self._last_signal.pop((room, active[0], "fragment"), None)
            previous = self._fragment_suppressed_until.get(room)
            if previous is None or until > previous:
                self._fragment_suppressed_until[room] = until

    def _get_kiwi(self):
        if self._kiwi_attempted:
            return self._kiwi
        with self._lock:
            if self._kiwi_attempted:
                return self._kiwi
            self._kiwi_attempted = True
            try:
                from kiwipiepy import Kiwi

                self._kiwi = Kiwi(model_type="cong", num_workers=1)
            except (ImportError, OSError):
                self._kiwi = None
        return self._kiwi

    @staticmethod
    def _clean_text(text: str) -> str:
        return _SPACE.sub(" ", (text or "").strip())[:160]

    def is_eums_style(self, text: str) -> tuple[bool, bool]:
        clean = self._clean_text(text)
        if not clean or not _EUMS_PREFILTER.search(clean):
            return False, False

        kiwi = self._get_kiwi()
        if kiwi is None:
            return bool(_FALLBACK_EUMS.search(clean)), False

        try:
            tokens = kiwi.tokenize(_TRAILING_NOISE.sub("", clean))
        except (ValueError, RuntimeError):
            return bool(_FALLBACK_EUMS.search(clean)), False
        if not tokens:
            return False, True

        last = tokens[-1]
        is_ending = last.tag == "EF" and last.form in {"음", "ㅁ", "ᆷ", "슴"}
        return is_ending, True

    @staticmethod
    def _is_fragment_candidate(text: str) -> bool:
        compact = text.replace(" ", "")
        return bool(compact) and not text.startswith("/")

    @staticmethod
    def _is_complete_message(text: str) -> bool:
        raw = text.strip()
        if raw.endswith((".", "!", "?")):
            return True
        clean = _TRAILING_NOISE.sub("", raw)
        return clean in _COMPLETE_SHORT_MESSAGES or bool(_COMPLETE_ENDING.search(clean))

    def _fragment_score(self, messages: list[_TimedMessage]) -> tuple[float, bool]:
        if self._predictor is not None:
            try:
                score, used = self._predictor.predict_fragment(
                    tuple(item.text for item in messages)
                )
                if used:
                    return float(score), True
            except (OSError, RuntimeError, ValueError):
                pass
        return self._fragment_rule_score(messages), False

    def _fragment_rule_score(self, messages: list[_TimedMessage]) -> float:
        """학습 모델이 없을 때 사용하는 보수적인 결합 가능성 점수."""
        if len(messages) < 2:
            return 0.0
        earlier = messages[:-1]
        incomplete = sum(not self._is_complete_message(item.text) for item in earlier)
        if incomplete == 0:
            return 0.32
        lengths = [len(item.text.replace(" ", "")) for item in messages]
        score = 0.52 + (incomplete / len(earlier)) * 0.2
        if max(lengths) <= 14:
            score += 0.08
        if len(messages) >= 3:
            score += 0.04
        return min(0.95, score)

    def analyze(
        self,
        room: str,
        user_key: str,
        text: str,
        settings: ModerationSettings,
        now: datetime | None = None,
    ) -> list[ModerationSignal]:
        if not settings.enabled:
            return []
        clean = self._clean_text(text)
        if not clean or clean.startswith("/"):
            return []

        current = now or datetime.now(timezone.utc)
        eums, kiwi_used = self.is_eums_style(clean)
        rule_eums = eums
        eums_model_score = 0.0
        eums_model_used = False
        if self._predictor is not None:
            try:
                eums_model_score, eums_model_used = self._predictor.predict_eums(clean)
            except (OSError, RuntimeError, ValueError):
                eums_model_score, eums_model_used = 0.0, False
        if eums_model_used:
            # 형태소 분석이 종결형을 확실히 잡은 경우에는 모델이 강한 오탐
            # 신호를 내지 않는 한 살린다. 모델 단독으로도 새로운 표현을 찾는다.
            eums = eums_model_score >= 0.62 or (
                rule_eums and eums_model_score >= 0.45
            )
        key = (room, user_key)
        signals: list[ModerationSignal] = []

        with self._lock:
            bucket = self._messages[key]
            keep_after = current - timedelta(minutes=10)
            while bucket and bucket[0].at < keep_after:
                bucket.popleft()
            bucket.append(_TimedMessage(current, clean, eums))

            suppressed_until = self._fragment_suppressed_until.get(room)
            fragment_suppressed = (
                suppressed_until is not None and current < suppressed_until
            )
            if suppressed_until is not None and not fragment_suppressed:
                self._fragment_suppressed_until.pop(room, None)

            fragments: list[_TimedMessage] = []
            if fragment_suppressed:
                active = self._fragment_runs.pop(room, None)
                if active is not None:
                    self._last_signal.pop((room, active[0], "fragment"), None)
            else:
                fragment_after = current - timedelta(
                    seconds=settings.fragment_window_seconds
                )
                active = self._fragment_runs.get(room)
                if active is None or active[0] != user_key:
                    if active is not None:
                        self._last_signal.pop((room, active[0], "fragment"), None)
                    fragment_run: deque[_TimedMessage] = deque()
                    self._fragment_runs[room] = (user_key, fragment_run)
                else:
                    fragment_run = active[1]

                if fragment_run and fragment_run[-1].at < fragment_after:
                    fragment_run.clear()
                    self._last_signal.pop((room, user_key, "fragment"), None)
                while fragment_run and fragment_run[0].at < fragment_after:
                    fragment_run.popleft()
                if self._is_fragment_candidate(clean):
                    fragment_run.append(_TimedMessage(current, clean, eums))

                fragments = list(fragment_run)
            required = max(2, settings.fragment_count)
            if len(fragments) >= required:
                # 기준 횟수에 도달한 뒤 같은 흐름으로 이어진 메시지도 모두
                # 관리자 판정 화면에서 볼 수 있도록 현재 관찰창 전체를 담는다.
                selected = fragments
                lengths = [len(item.text.replace(" ", "")) for item in selected]
                duration = (selected[-1].at - selected[0].at).total_seconds()
                combined_length = sum(lengths)
                average = combined_length / len(selected)
                cooldown_key = (room, user_key, "fragment")
                last = self._last_signal.get(cooldown_key)
                is_new_signal = last is None or (current - last).total_seconds() >= 60
                continues_signal = last is not None and any(
                    item.at <= last for item in selected
                )
                merge_score, model_used = self._fragment_score(selected)
                threshold = 0.62 if model_used else 0.55
                if merge_score >= threshold and (is_new_signal or continues_signal):
                    score = min(0.99, merge_score + min(0.12, len(selected) * 0.02))
                    signals.append(
                        ModerationSignal(
                            kind="fragment",
                            score=round(score, 3),
                            messages=tuple(item.text for item in selected),
                            features={
                                "message_count": len(selected),
                                "average_length": round(average, 2),
                                "max_length": max(lengths),
                                "duration_seconds": round(duration, 2),
                                "combined_length": combined_length,
                                "continuation": continues_signal,
                                "merge_score": round(merge_score, 3),
                                "model_used": model_used,
                            },
                            sent_at=tuple(item.at.isoformat() for item in selected),
                        )
                    )
                    self._last_signal[cooldown_key] = current

            eums_messages = [item for item in bucket if item.eums]
            eums_required = max(1, settings.eums_count)
            if len(eums_messages) >= eums_required:
                selected = eums_messages[-eums_required:]
                cooldown_key = (room, user_key, "eums")
                last = self._last_signal.get(cooldown_key)
                if last is None or (current - last).total_seconds() >= 600:
                    score = min(0.98, 0.62 + len(selected) * 0.07)
                    signals.append(
                        ModerationSignal(
                            kind="eums",
                            score=round(score, 3),
                            messages=tuple(item.text for item in selected),
                            features={
                                "message_count": len(selected),
                                "window_seconds": round(
                                    (selected[-1].at - selected[0].at).total_seconds(), 2
                                ),
                                "kiwi_used": kiwi_used,
                                "model_used": eums_model_used,
                                "model_score": round(eums_model_score, 3),
                            },
                            sent_at=tuple(item.at.isoformat() for item in selected),
                        )
                    )
                    self._last_signal[cooldown_key] = current

            if not bucket:
                self._messages.pop(key, None)

        return signals


def preview_messages(messages: tuple[str, ...], limit: int = 240) -> str:
    preview = " / ".join(message.strip() for message in messages if message.strip())
    return preview[:limit]
