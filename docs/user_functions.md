# User Function Guide

This guide summarizes the tools available in this repository and how to call them from Puch AI.

## Job Finder
Analyze job descriptions, fetch postings from URLs, or search for roles.
Example:
```
/mcp run job_finder {"user_goal": "Find remote Python roles", "job_url": "https://example.com/job"}
```

## Translation
Translate text between languages using Google Translate.
Example:
```
/mcp run translate {"text": "Hello", "target_lang": "es"}
```

## Image Processor
Convert images to black and white.
Example:
```
/mcp run make_img_black_and_white {"puch_image_data": "<base64>"}
```

## Spotify Controls
Play and control Spotify playback (play, pause, next, previous, current track).
Example:
```
/mcp run play {"track_id": "4uLU6hMCjMI75M1A2tKUQC"}
```

## Expense Tracker
Record expenses and view summaries.
Examples:
```
/mcp run add_expense {"phone": "+15550000000", "amount": 25, "category": "food"}
/mcp run weekly_summary {"phone": "+15550000000"}
```

## News Headlines
Fetch top headlines using the NewsAPI service. You can filter by search term, country or category and the tool returns the raw JSON from the API.
Example:
```
/mcp run headlines {"country": "us", "category": "technology", "limit": 3}
```

## Utility Dispatcher
Handy utilities like currency conversion, unit conversion, time lookup, bill splitting, age calculation and expression evaluation.
Example:
```
/mcp run split_bill {"total": 120, "num_people": 4, "tip_percent": 15}
```

## Calculator
Evaluate mathematical expressions via a dedicated MCP server.
Example:
```
/mcp run calculate {"expression": "sin(pi/2) + 2**3"}
```

## OAuth Examples
Sample projects for OAuth flows with Google and GitHub. Deploy the workers and connect from Puch AI to authorize and call protected tools.
Example workflow:
```
/mcp connect https://your-oauth-worker.example/mcp
```
