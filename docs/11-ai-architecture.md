# AI Architecture

## Providers

`LLMProvider`, `EmbeddingProvider`, `RerankerProvider`, `SpeechToTextProvider`, `TextToSpeechProvider`, `VisionProvider`.

MVP implements LLM, embeddings, and uploaded-audio transcription: `Gemini` + `Mock`. Chat uses `generateContent`. Embeddings use `batchEmbedContents`. Uploaded audio is inline `generateContent`.

## Router

Task → ModelRouter → model selected for quality, cost, latency, privacy, context length. Model names come from environment, never hardcoded defaults in business code.

## Cost

Every completion writes `model_usage`: provider, model, agent, prompt version, tokens, latency, estimated cost.

## Evaluation

Accuracy, groundedness, citation quality, tool correctness, safety, latency, cost, task success. Offline eval lives in `ai/evaluation`.
