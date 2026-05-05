import requests

def chat_with_qwen(messages):
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen2.5:3b",
        "messages": messages,
        "stream": False
    }
     
    response = requests.post(url, json=payload)
    return response.json().get("message", {}).get("content", "")

messages = [
    {"role": "user", "content": "Hello, who are you?"}
]

reply = chat_with_qwen(messages)
print(reply)