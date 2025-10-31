# Interview Question Generation System

## Overview

The interview question generation system uses Claude Opus (Claude API) to automatically generate thoughtful, well-structured interview questions for podcast episodes. It incorporates podcast context, SEO keywords, and guest information to create questions tailored to your show.

## Directory Structure

```
vault/
└── workflows/
    └── podcast_context/
        ├── interview_prompt.md       # Main prompt template for Claude
        ├── podcast_context.txt       # Podcast themes and information
        └── seo_keywords.txt          # Keywords to naturally incorporate
```

## Files

### interview_prompt.md
The main prompt template that guides Claude in generating questions. It includes:
- Guidelines for three-section structure (Opening, Main Discussion, Closing)
- Tone and style guidelines
- Placeholder variables filled in at runtime:
  - `{GUEST_NAME}` - Name of the interviewee
  - `{GUEST_BACKGROUND}` - Background info (extracted from transcript or provided)
  - `{KEY_TOPICS}` - Topics to discuss
  - `{SEO_KEYWORDS}` - List of keywords to incorporate
  - `{PODCAST_CONTEXT}` - Your podcast's mission and themes

### podcast_context.txt
Background information about your podcast including:
- Core themes (Quiet Confidence, Authentic Leadership, etc.)
- Target audience
- Host perspective

### seo_keywords.txt
Comma-separated or newline-separated keywords that are naturally woven into questions. Examples:
- Introvert Leadership
- Quiet Confidence
- Authentic Leadership
- Emotional Intelligence
- etc.

## CLI Command

### Basic Usage

```bash
# Generate questions for a guest
zk generate-questions "Guest Name"

# With transcript analysis
zk generate-questions "Guest Name" --transcript path/to/prep-transcript.txt

# With custom background and topics
zk generate-questions "Guest Name" \
  --background "Guest's background info" \
  --topics "Topic 1, Topic 2, Topic 3"

# Save to file
zk generate-questions "Guest Name" --output interview-questions.md
```

### Options

- `--transcript, -t`: Path to prep conversation transcript (optional)
  - If provided, Claude analyzes it to extract background and key topics
  - Falls back to provided values or defaults if file is empty

- `--background, -b`: Guest background information (optional)
  - Overrides extraction from transcript
  - Can be used alone or with transcript

- `--topics, -k`: Key topics to discuss (optional)
  - Overrides extraction from transcript
  - Format: "Topic 1, Topic 2, Topic 3"

- `--output, -o`: Output file path (optional)
  - If not provided, questions print to stdout
  - Creates markdown file ready to use

### Examples

```bash
# Generate questions and display in terminal
zk generate-questions "Steven Puri"

# Extract from transcript and save
zk generate-questions "Diane Taylor" \
  --transcript "Documents/podcast-video/Diane Taylor/prep conversation transcript.txt" \
  --output "Documents/podcast-video/Diane Taylor/interview questions.md"

# Quick generation with manual input
zk generate-questions "Grant Harris" \
  --background "Leadership coach from San Francisco" \
  --topics "Quiet confidence, Authentic leadership, Emotional intelligence" \
  --output interview-questions.md
```

## How It Works

### Question Generation Process

1. **Load Templates**: Reads prompt, context, and keywords from `podcast_context/` directory

2. **Extract Information** (optional):
   - If transcript provided, Claude analyzes it to extract:
     - Guest background (2-3 sentences)
     - Key topics (5-7 bullet points)
   - Uses these or provided values for question generation

3. **Generate Questions**:
   - Claude receives a system prompt with all context
   - Generates 3 sections of questions:
     - **Opening** (2-3): Build rapport, introduce topics
     - **Main Discussion** (6-8): Deep dive into expertise, incorporate keywords
     - **Closing** (2-3): Reflections, actionable insights, inspiration

4. **Output**:
   - Returns markdown-formatted questions
   - Optionally saves to file

### AI Model

Uses **Claude Opus 4.1** (`claude-opus-4-1-20250805`):
- Best for complex, nuanced question generation
- Handles long context effectively
- Natural language generation quality is excellent
- More capable than Claude Haiku for this task

## Customization

### Updating Podcast Context

Edit `vault/workflows/podcast_context/podcast_context.txt` to reflect:
- Current podcast themes
- Target audience information
- Host perspective and values

### Updating Keywords

Edit `vault/workflows/podcast_context/seo_keywords.txt` to add or modify keywords you want naturally incorporated into questions.

### Modifying the Prompt

Edit `vault/workflows/podcast_context/interview_prompt.md` to:
- Change question structure (e.g., different number of questions per section)
- Adjust tone or style
- Add specific topics or angles
- Change markdown formatting

## Integration with Episode Workflow

Future enhancements could:
1. Automatically trigger question generation when `zk episode import` is run
2. Auto-save questions to `interview questions.md` in episode directory
3. Extract guest info from RSS feed or index.md for automatic background/topics

## Notes

- **Transcript Analysis**: Best results when prep transcript contains actual conversation content
- **Background/Topics**: If no transcript provided, you can manually provide these for faster generation
- **SEO Keywords**: Claude naturally incorporates them; check output to ensure they fit naturally
- **Customization**: Adjust templates and context to match your show's specific needs and style

## Example Output

```markdown
# Interview Questions - Steven Puri

**Guest:** Steven Puri

## Opening Questions

1. Steven, welcome to the Powerful Introvert Podcast! I'd love to start...
2. Many of our listeners struggle with...
3. Before we dive deeper...

## Main Discussion

1. Let's talk about quiet confidence...
2. The power of listening...
[etc.]

## Closing Questions

1. For our listeners who are introverts...
2. Looking ahead...
3. If you could go back...
```

---

This system replaces manual ChatGPT-based question generation with a fully integrated, customizable workflow using Claude API.
