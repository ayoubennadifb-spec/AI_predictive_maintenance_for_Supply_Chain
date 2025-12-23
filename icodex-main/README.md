# ICodeX Model

ICodeX is an AI-driven evaluation system with:
- A **PDF → quiz** generation pipeline (Cerebras LLM + ReportLab PDF export)
- An **answer evaluator** that computes performance metrics
- A **mastery scorer** that turns metrics into a 0–100 score
- A **question recommender** that picks the next question based on performance
- A **web app** (FastAPI backend + React frontend) for admin/teacher/student flows

## Repo layout
- `questions generator/`: PDF→text, chunking, structuring, question generation, quiz→PDF
- `answers evaluation/`: `answer_evaluator.py`, `mastery_scorer.py`
- `questions recommander/`: `question_recommender.py` (adaptive selection)
- `interface/icodex_webapp/`: FastAPI backend + minimal template UI + runtime state
- `interface/icodex_figma_interface/`: React + Vite frontend (Figma “Redesign ICodex Web App”)

## Quickstart (dev)

### 1) Backend (FastAPI)
```cmd
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt

set CEREBRAS_API_KEY=csk-REPLACE_ME
python run.py
```

### 2) Frontend (React + Vite)
```cmd
cd interface\icodex_figma_interface
npm install
npm run dev
```
Then open `http://localhost:3000` (Vite proxies `/api` to `http://localhost:8001`).

## Pipeline data flow (contracts)
1) `*.pdf` → `*_extracted.txt`
2) `*_extracted.txt` → `*_extracted_chunks.json`
   - `{ total_chunks, chunks: [{ id, text, char_count, word_count }] }`
3) `*_extracted_chunks.json` → `*_extracted_chunks_structure.json`
   - Nested hierarchy: `course -> modules -> mini_modules -> concepts -> mini_concepts`
4) `*_structure.json` → `*_quiz.json`
   - Adds `questions: [{ question, options[4], correct_answer, difficulty? }]` on titled nodes
5) (optional) annotate difficulty: `*_quiz.json` → `*_quiz.json` (in-place)
6) `*_quiz.json` → `*_quiz.pdf`

## Run the pipeline (CLI)
```cmd
cd "questions generator"
set CEREBRAS_API_KEY=csk-REPLACE_ME

python files_to_text.py --source-dir path\\to\\materials --output merged_raw.txt
python text_rewriter.py --input merged_raw.txt --output merged_cleaned.txt --model llama3.1-8b
python text_to_chunks.Py -i merged_cleaned.txt
python chunks_to_structure.py -i merged_cleaned_chunks.json
python structure_to_questions.Py -i merged_cleaned_chunks_structure.json
python difficulty_assessor.py -i merged_cleaned_chunks_structure_quiz.json --in-place
python quiz_to_pdf.py -i merged_cleaned_chunks_structure_quiz.json
```

## Notes
- Runtime state and generated artifacts are stored under `interface/icodex_webapp/data/` and should not be committed.
- On Render, the filesystem is ephemeral by default. For persistence:
  - Use Postgres for app state by setting `DATABASE_URL` (recommended for free tiers).
  - Use a Render Disk for files (PDF uploads + generated PDFs) and set `ICODEX_DATA_DIR` to the disk mount path (see `.env.example`).
- Never commit real API keys. Use `.env.example` as a template.
