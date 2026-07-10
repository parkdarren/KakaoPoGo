package com.kakaopogo.bridge;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.Intent;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class KakaoNotificationService extends NotificationListenerService {
    private static final String KAKAO_PACKAGE = "com.kakao.talk";
    private static final int DEDUPE_LIMIT = 80;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final LinkedHashMap<String, Boolean> seenNotifications = new LinkedHashMap<String, Boolean>() {
        @Override
        protected boolean removeEldestEntry(Map.Entry<String, Boolean> eldest) {
            return size() > DEDUPE_LIMIT;
        }
    };

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (!BotConfig.isEnabled(this)) {
            return;
        }
        if (sbn == null || !KAKAO_PACKAGE.equals(sbn.getPackageName())) {
            return;
        }

        Notification notification = sbn.getNotification();
        if (notification == null) {
            return;
        }

        RemoteReplyAction replyAction = findReplyAction(notification);
        if (replyAction == null) {
            return;
        }

        MessageInfo message = extractMessage(notification);
        if (message.text.isEmpty() || !isCommand(message.text)) {
            return;
        }

        String dedupeKey = sbn.getKey() + "|" + sbn.getPostTime() + "|" + message.text;
        synchronized (seenNotifications) {
            if (seenNotifications.containsKey(dedupeKey)) {
                return;
            }
            seenNotifications.put(dedupeKey, true);
        }

        log("Command: room=" + message.room + ", sender=" + message.sender + ", text=" + message.text);
        executor.execute(() -> handleCommand(message, replyAction));
    }

    private void handleCommand(MessageInfo message, RemoteReplyAction replyAction) {
        try {
            String reply = BotHttpClient.command(
                    BotConfig.serverUrl(this),
                    message.text,
                    message.room,
                    message.sender
            );
            if (reply.trim().isEmpty()) {
                log("Empty server reply");
                return;
            }
            sendReply(replyAction, reply);
            log("Replied: " + firstLine(reply));
        } catch (Exception e) {
            log("Failed: " + e.getMessage());
        }
    }

    private MessageInfo extractMessage(Notification notification) {
        Bundle extras = notification.extras == null ? new Bundle() : notification.extras;
        String title = charSequence(extras.getCharSequence(Notification.EXTRA_TITLE));
        String text = charSequence(extras.getCharSequence(Notification.EXTRA_TEXT));
        String room = charSequence(extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE));
        String sender = title;

        Object[] messages = null;
        Object rawMessages = extras.get(Notification.EXTRA_MESSAGES);
        if (rawMessages instanceof Object[]) {
            messages = (Object[]) rawMessages;
        }

        if (messages != null && messages.length > 0) {
            Object last = messages[messages.length - 1];
            if (last instanceof Bundle) {
                Bundle bundle = (Bundle) last;
                String bundledText = charSequence(bundle.getCharSequence("text"));
                if (!bundledText.isEmpty()) {
                    text = bundledText;
                }
                Object senderPerson = bundle.get("sender_person");
                if (senderPerson != null) {
                    String personText = senderPerson.toString();
                    if (!personText.isEmpty()) {
                        sender = personText;
                    }
                }
                String bundledSender = charSequence(bundle.getCharSequence("sender"));
                if (!bundledSender.isEmpty()) {
                    sender = bundledSender;
                }
            }
        }

        if (room.isEmpty()) {
            String subText = charSequence(extras.getCharSequence(Notification.EXTRA_SUB_TEXT));
            room = subText.isEmpty() ? title : subText;
        }
        if (sender.isEmpty()) {
            sender = title.isEmpty() ? "unknown" : title;
        }
        if (room.isEmpty()) {
            room = "unknown";
        }

        return new MessageInfo(room, sender, text.trim());
    }

    private RemoteReplyAction findReplyAction(Notification notification) {
        if (notification.actions == null) {
            return null;
        }

        RemoteReplyAction fallback = null;
        for (Notification.Action action : notification.actions) {
            RemoteInput[] inputs = action.getRemoteInputs();
            if (inputs == null || inputs.length == 0) {
                continue;
            }
            RemoteReplyAction candidate = new RemoteReplyAction(action, inputs);
            String title = charSequence(action.title).toLowerCase(Locale.ROOT);
            if (title.contains("reply") || title.contains("답장")) {
                return candidate;
            }
            if (fallback == null) {
                fallback = candidate;
            }
        }
        return fallback;
    }

    private void sendReply(RemoteReplyAction replyAction, String reply) throws PendingIntent.CanceledException {
        Intent intent = new Intent();
        Bundle results = new Bundle();
        for (RemoteInput input : replyAction.remoteInputs) {
            results.putCharSequence(input.getResultKey(), reply);
        }
        RemoteInput.addResultsToIntent(replyAction.remoteInputs, intent, results);
        replyAction.action.actionIntent.send(this, 0, intent);
    }

    private boolean isCommand(String text) {
        return text.startsWith("/");
    }

    private String firstLine(String text) {
        int newline = text.indexOf('\n');
        return newline >= 0 ? text.substring(0, newline) : text;
    }

    private String charSequence(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private void log(String message) {
        String stamp = new SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(new Date());
        BotConfig.appendLog(this, "[" + stamp + "] " + message);
    }

    private static final class MessageInfo {
        final String room;
        final String sender;
        final String text;

        MessageInfo(String room, String sender, String text) {
            this.room = room;
            this.sender = sender;
            this.text = text;
        }
    }

    private static final class RemoteReplyAction {
        final Notification.Action action;
        final RemoteInput[] remoteInputs;

        RemoteReplyAction(Notification.Action action, RemoteInput[] remoteInputs) {
            this.action = action;
            this.remoteInputs = remoteInputs;
        }
    }
}
