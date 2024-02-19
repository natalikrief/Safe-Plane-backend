def test():
    import openai

    # Set your OpenAI API key
    openai.api_key = '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'  # 'safe-plane-key'

    # Define a prompt for the chat-based conversation
    prompt = "You are a helpful assistant."

    # Example conversation
    conversation_history = [
        {"role": "user", "content": "Who won the world series in 2020?"},
        {"role": "assistant", "content": "The Los Angeles Dodgers won the World Series in 2020."},
        {"role": "user", "content": "Where was it played?"}
    ]

    # Combine prompt and conversation
    input_data = {"messages": [{"role": "system", "content": "You are a helpful assistant."}] + conversation_history}

    # Call OpenAI API
    response = openai.Completion.create(
        engine="gpt-3.5-turbo",  # Use a GPT-3.5 engine
        prompt=prompt,
        messages=input_data,
        max_tokens=150  # Adjust based on your needs
    )

    # Extract assistant's reply from the API response
    reply = response['choices'][0]['message']['content']

    # Print the assistant's reply
    print("Assistant:", reply)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    test()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
