# Audio Generation Concurrency Improvements

## Overview

The audio generation system has been enhanced with concurrent processing capabilities to significantly improve performance when generating multiple audio files. This implementation follows best practices from the OpenAI rate limiting documentation.

## Key Improvements

### 1. Asynchronous Audio Generation

**File: `audio_handler.py`**

- Added async support for both ElevenLabs and OpenAI providers
- Implemented `generate_audio_async()` method for single audio generation
- Added `generate_multiple_audio()` method for batch processing multiple audio files concurrently
- Maintained backward compatibility with synchronous `generate_audio()` method

### 2. Concurrent Request Management

- **Semaphore Control**: Limits concurrent requests to prevent overwhelming the API
- **Rate Limiting**: Tracks requests per minute and enforces limits
- **Automatic Retry**: Uses exponential backoff with the `@backoff` decorator
- **Error Handling**: Proper handling of 429 (rate limit) errors with retry logic

### 3. Batch Processing in Master Processor

**File: `master_scripture_processor.py`**

- Modified `process_verses()` to use async batch processing
- Collects all verses that need audio generation into a batch
- Processes the entire batch concurrently instead of sequentially
- Maintains database consistency while leveraging parallel processing

## Configuration

Add these settings to your `config.json`:

```json
"audio_generation": {
    "max_concurrent_requests": 5,    // Maximum parallel requests
    "requests_per_minute": 60,       // Rate limit per minute
    // ... other settings
}
```

### Recommended Settings by Provider:

**OpenAI (Free Tier)**:
- `max_concurrent_requests`: 3-5
- `requests_per_minute`: 60

**OpenAI (Paid Tiers)**:
- Tier 1-2: `max_concurrent_requests`: 5-10
- Tier 3-5: `max_concurrent_requests`: 10-20
- Adjust `requests_per_minute` based on your tier limits

**ElevenLabs**:
- Check your plan's rate limits
- Start conservative with `max_concurrent_requests`: 3-5

## Performance Improvements

Based on the concurrency implementation, you can expect:

- **3-5x faster** audio generation for batches of verses
- **Automatic rate limit handling** prevents API errors
- **Efficient resource usage** through connection pooling
- **Resilient processing** with automatic retries

## Usage Example

The system automatically uses concurrent processing when generating multiple audio files:

```python
# Old way (sequential):
# for verse in verses:
#     audio_handler.generate_audio(verse_text, output_path)

# New way (concurrent - happens automatically):
# All verses in a quest are processed in parallel
processor.run()  # Automatically uses concurrent processing
```

## Monitoring and Debugging

The system now uses Python's logging module for better visibility:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

You'll see messages like:
- `"Generating 50 audio files concurrently..."`
- `"Rate limit reached, waiting 15.2 seconds"`
- `"Low rate limit remaining: 5"`

## Error Handling

The system handles various error scenarios:

1. **Rate Limits**: Automatically waits and retries
2. **Network Errors**: Retries with exponential backoff
3. **API Errors**: Logs errors and continues with other requests
4. **Partial Failures**: Records which files succeeded/failed

## Dependencies

Install the required packages:

```bash
pip install -r requirements.txt
```

New dependencies added:
- `aiohttp`: For async HTTP requests
- `backoff`: For retry logic
- `asyncio`: For async/await support (usually built-in)

## Best Practices

1. **Start Conservative**: Begin with lower concurrency limits and increase gradually
2. **Monitor Rate Limits**: Watch the logs for rate limit warnings
3. **Test Load**: Run a small batch first to ensure your settings work
4. **Adjust for Peak Times**: API rate limits might be stricter during high-usage periods

## Troubleshooting

**Issue**: Getting rate limit errors
- **Solution**: Reduce `max_concurrent_requests` or `requests_per_minute`

**Issue**: Slow performance
- **Solution**: Increase `max_concurrent_requests` if under rate limits

**Issue**: Connection errors
- **Solution**: Check network stability, reduce concurrent requests

**Issue**: Memory usage high
- **Solution**: Process verses in smaller batches by reducing quest sizes 