import requests
import json

API_KEY = "sk-ur78CDqIf2MxGNuDBrHkhFD7eue9of8uND32UmJ0x4NA2CPl"
BASE_URL = "https://api.chatanywhere.tech"
ENDPOINT = "/v1/chat/completions"
MODEL_NAME = "deepseek-v4-pro"

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

# 初始化对话历史
conversation_history = [
    {"role": "system", "content": "你是一位乐于助人的AI助手。"}
]

def chat(user_message, max_tokens=150, temperature=0.7):
    """发送消息并获取回复"""
    # 将用户消息添加到对话历史
    conversation_history.append({"role": "user", "content": user_message})
    
    data = {
        "model": MODEL_NAME,
        "messages": conversation_history,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    url = f"{BASE_URL}{ENDPOINT}"
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        
        if result.get("choices"):
            reply_content = result["choices"][0]["message"]["content"]
            # 将助手回复添加到对话历史
            conversation_history.append({"role": "assistant", "content": reply_content})
            return reply_content
        else:
            print("\n--- API 响应异常 ---")
            print("未找到 choices，完整响应：")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"\n--- 请求失败 ---")
        print(f"发生错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print("错误详情:")
                print(json.dumps(error_details, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print("无法解析错误响应体。")
                print(f"状态码: {e.response.status_code}")
        return None
        
    except Exception as e:
        print(f"\n发生未知错误: {e}")
        return None

def main():
    """主对话循环"""
    print(f"连接到: {BASE_URL}{ENDPOINT}")
    print(f"使用的模型: {MODEL_NAME}")
    print("\n开始对话（输入 'quit' 或 'exit' 退出，输入 'clear' 清空历史）\n")
    
    while True:
        try:
            user_input = input("你: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['quit', 'exit', '退出']:
                print("对话结束。再见！")
                break
                
            if user_input.lower() in ['clear', '清空']:
                conversation_history.clear()
                conversation_history.append({"role": "system", "content": "你是一位乐于助人的AI助手。"})
                print("对话历史已清空。\n")
                continue
            
            reply = chat(user_input)
            
            if reply:
                print(f"\nAI: {reply}\n")
                
        except KeyboardInterrupt:
            print("\n\n对话被中断。再见！")
            break
        except EOFError:
            print("\n\n对话结束。再见！")
            break

if __name__ == "__main__":
    main()