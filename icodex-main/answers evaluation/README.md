# Answer Evaluation

This folder contains the scoring scripts used by `interface/icodex_webapp/app.py`:
- `answer_evaluator.py`: computes per-answer metrics/features
- `mastery_scorer.py`: converts metrics into a mastery score (0–100)

## CLI examples (Windows CMD)

Run the evaluator:
```cmd
python "answers evaluation\\answer_evaluator.py" --question "What is the purpose of the __name__ variable in Python?" --correct-answer "It is used to determine the current module name." --student-answer "It indicates whether the module is run directly or imported by exposing the module name" --time-taken 18 --expected-time 20 --difficulty medium --position "course/Real Python Pocket Reference"
```

Pipe evaluator output into mastery scoring:
```cmd
python "answers evaluation\\answer_evaluator.py" --question "What is the purpose of the __name__ variable in Python?" --correct-answer "It is used to determine the current module name." --student-answer "It indicates whether the module is run directly or imported by exposing the module name" --time-taken 18 --expected-time 20 --difficulty medium --position "course/Real Python Pocket Reference" | python "answers evaluation\\mastery_scorer.py" --input -
```
