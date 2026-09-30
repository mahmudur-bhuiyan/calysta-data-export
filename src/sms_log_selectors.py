# Selectors for patient SMS log / conversation page

SMS_LOG_URL = "https://www.calystaproemr.com/sms-details/index/{patient_id}"

CHAT_CONTAINER = ".entire-chat-bot"
MESSAGE_BUBBLE = ".entire-chat-bot .single-chat-bot"
SENDER_CHAT = "sender-chat"      # patient messages
RECEIVER_CHAT = "receiver-chat"  # facility messages
MESSAGE_TIME = ".time-right"
NO_RESULTS_TEXT = "no results found"

SMS_LOG_COLUMNS = [
    "patient_id",
    "type",
    "message",
    "category",
    "sent_on",
]
