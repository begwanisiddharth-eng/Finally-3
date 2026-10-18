---
name: groq-skill
description: Use this to write code to call an LLM using LiteLLM with the Groq inference provider
---

# Calling an LLM via Groq

These instructions allow you to write code to call an LLM with Groq specified as the inference provider.
This method uses LiteLLM directly against Groq.

Calls to Groq are rate limited. Retry with exponential backoff using the tenacity library.

## Setup

The GROQ_API_KEY must be set in the .env file and loaded in as an environment variable.

The uv project must include litellm, pydantic, and tenacity.
`uv add litellm pydantic tenacity`

## Code snippets

Use code like these examples in order to use Groq.

### Imports and constants

```python
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_exponential

MODEL = "groq/openai/gpt-oss-120b"
```

### Retry wrapper with exponential backoff

```python
@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
def call_llm(**kwargs):
    return completion(**kwargs)
```

### Code to call via Groq for a text response

```python
response = call_llm(model=MODEL, messages=messages, reasoning_effort="low")
result = response.choices[0].message.content
```

### Code to call via Groq for a Structured Outputs response

```python
response = call_llm(model=MODEL, messages=messages, response_format=MyBaseModelSubclass, reasoning_effort="low")
result = response.choices[0].message.content
result_as_object = MyBaseModelSubclass.model_validate_json(result)
```
