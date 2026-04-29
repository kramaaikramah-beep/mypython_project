# Assignment Format Guide

## Purpose

This document explains how student assignments should be formatted so the AI Assessment Checker can read them correctly and return reliable assessor-style feedback.

The system works best when the document has a clear question-and-answer structure. It reads the uploaded file, detects each question, captures the student answer under that question, and then reviews the response.

## Supported File Types

The application currently supports:

- `.docx`
- `.pdf`

For the best results, use `.docx` whenever possible. Word documents preserve structure more clearly than PDFs.

## Recommended Assignment Structure

Each question should be written clearly, and the student answer should appear directly underneath it.

Recommended format:

```text
Assessment Title

Student Name: John Smith

Q1. Explain the importance of workplace communication.

Student answer goes here.
The answer can continue on multiple lines.

Q2. Describe two barriers to communication and how they can be reduced.

Student answer goes here.

Q3. Explain why feedback is important in a workplace environment.

Student answer goes here.
```

## Question Formats The Engine Can Detect

The engine is designed to detect common question labels such as:

- `Q1`
- `Q1.`
- `Q1:`
- `Question 1`
- `Question 1.`
- `Question 1:`
- `Task 1`
- `Task 1:`
- `Section 1`
- `1.`

Use one consistent question style throughout the whole file.

## Best Practice Rules

To help the engine review the assignment correctly, follow these rules:

- Put each question on its own line.
- Put the student answer directly below the question.
- Keep each answer under the correct question.
- Use clear numbering such as `Q1`, `Q2`, `Q3`.
- Leave a line break between one answer and the next question.
- Keep the document text selectable and readable.
- If possible, use normal paragraphs instead of screenshots or images of text.

## Example Of A Good Format

```text
Q1. What is effective communication?

Effective communication is the clear exchange of information between people.
It helps reduce misunderstandings and improves teamwork in the workplace.

Q2. What are two communication barriers?

Two common barriers are language differences and poor listening.
These can be reduced by using simple language, checking understanding,
and asking follow-up questions.
```

## Formats That Cause Problems

The engine may produce weak or incorrect mapping if the file has problems like these:

- multiple questions written in one paragraph
- answers not placed under the correct question
- no question numbers or labels
- scanned image PDFs with poor text extraction
- tables with complex layouts
- handwritten content
- answer text mixed across headers, footers, or text boxes

Example of a bad structure:

```text
Q1 and Q2 are answered together in one block without separation.
The engine may not know where one answer ends and the next begins.
```

## If You Upload An Answer Sheet

If an assessor answer sheet is uploaded, the system uses it as extra review context.

For best results:

- keep the question order similar to the student file
- use matching question numbers where possible
- upload the answer sheet as `.docx` or readable `.pdf`

## How The Review Engine Works

The application follows this process:

1. Read the uploaded student file.
2. Detect question sections from the document.
3. Capture the answer under each question.
4. Send the content to the review engine.
5. Generate assessor-style feedback.
6. Return the same file with feedback inserted.

If Claude AI is available, the app uses Claude as the main assessor engine.
If Claude is unavailable or returns an incomplete response, the app uses the local fallback review logic.

## Recommended Client Instruction

You can give this instruction to assessors or students:

```text
Please upload the assignment in DOCX or readable PDF format.
Use a clear question-and-answer structure.
Write each question as Q1, Q2, Q3 or Question 1, Question 2, Question 3.
Place each student answer directly below its question.
Do not combine multiple answers into one section.
```

## Final Recommendation

For the most reliable review quality:

- use `.docx`
- use `Q1`, `Q2`, `Q3` style numbering
- keep one question and one answer section at a time
- avoid complex tables and scanned-image PDFs

This format gives the engine the best chance of detecting each answer correctly and producing useful assessor-style feedback.
