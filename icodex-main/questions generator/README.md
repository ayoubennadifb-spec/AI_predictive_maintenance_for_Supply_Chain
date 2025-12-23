# Questions Generator (PDF → Quiz Pipeline)

Turn any PDF into a structured, multi-choice quiz (JSON + PDF).

## Pipeline steps
1) `files_to_text.py` → merge text from PDF/DOCX/PPTX into `<stem>_merged_raw.txt`
2) `text_rewriter.py` → clean deduped text into `<stem>_merged_cleaned.txt`
3) `text_to_chunks.Py` → `<stem>_extracted_chunks.json`
4) `chunks_to_structure.py` → `<stem>_extracted_chunks_structure.json`
5) `structure_to_questions.Py` → `<stem>_extracted_chunks_structure_quiz.json`
6) `difficulty_assessor.py` → annotate each question with difficulty (easy|medium|hard)
7) `quiz_to_pdf.py` → `<stem>_extracted_chunks_structure_quiz.pdf`

## Install
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure Cerebras key
```powershell
$Env:CEREBRAS_API_KEY = "csk-REPLACE_ME"
```

## Run (example)
```powershell
python files_to_text.py --source-dir path\\to\\materials --output merged_raw.txt
python text_rewriter.py --input merged_raw.txt --output merged_cleaned.txt --model llama3.1-8b
python text_to_chunks.Py -i merged_cleaned.txt -o your_extracted_chunks.json --model llama3.1-8b
python chunks_to_structure.py -i your_extracted_chunks.json -o your_extracted_chunks_structure.json
python structure_to_questions.Py -i your_extracted_chunks_structure.json -o your_extracted_chunks_structure_quiz.json
python difficulty_assessor.py -i your_extracted_chunks_structure_quiz.json --in-place
python quiz_to_pdf.py -i your_extracted_chunks_structure_quiz.json -o your_extracted_chunks_structure_quiz.pdf
```

## Notes
- `quiz_to_pdf.py` will render difficulty when `difficulty_assessor.py` added it to each question.
