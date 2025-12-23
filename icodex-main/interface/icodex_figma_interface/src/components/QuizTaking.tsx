import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { X, Clock, CheckCircle, Trophy, Download } from "lucide-react";
import { Button } from "./Button";
import { Card } from "./Card";
import { ProgressBar } from "./ProgressBar";
import { Chip } from "./Chip";
import { api } from "../utils/api";
import { useToast } from "./Toast";

interface QuizTakingProps {
  mode: "assigned" | "practice";
  assignmentId?: string;
  testId?: string;
  onExit: () => void;
}

interface Question {
  id: string;
  question: string;
  options: string[];
  correct_answer?: string;
  section?: string;
  difficulty?: string;
}

export function QuizTaking({ mode, assignmentId, testId, onExit }: QuizTakingProps) {
  const { showToast } = useToast();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [current, setCurrent] = useState<Question | null>(null);
  const [asked, setAsked] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<"quiz" | "completion">("quiz");
  const [score, setScore] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [debugPayload, setDebugPayload] = useState<any>(null);
  const [showDebug, setShowDebug] = useState(false);
  const [total, setTotal] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [userId, setUserId] = useState<string | null>(null);
  const [resolvedTestId, setResolvedTestId] = useState<string | null>(null);
  const [questionNumber, setQuestionNumber] = useState(1);
  const [assignedQuestionNumber, setAssignedQuestionNumber] = useState(1);
  const [assignedLimit, setAssignedLimit] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [questionStartedAt, setQuestionStartedAt] = useState<number | null>(null);
  const [reviewMode, setReviewMode] = useState(false);
  const [feedback, setFeedback] = useState<any>(null);
  const [pendingQuestion, setPendingQuestion] = useState<Question | null>(null);
  const [pendingMeta, setPendingMeta] = useState<any>(null);
  const [sessionXp, setSessionXp] = useState<any | null>(null);
  const [achievementsUnlocked, setAchievementsUnlocked] = useState<string[]>([]);

  const startPractice = async () => {
    if (!testId) return;
    const data = await api<any>("/api/practice/start", {
      method: "POST",
      body: JSON.stringify({ test_id: testId }),
    });
    setDebugPayload({ mode: "practice-start", data });
    const q = data.question;
    if (!q) throw new Error("No question returned");
    setCurrent({
      id: q.id || q.question,
      question: q.question,
      options: q.options || [],
      correct_answer: q.correct_answer,
      section: q.section,
      difficulty: q.difficulty,
    });
    setAsked([q.question]);
    setResolvedTestId(String(testId));
    const limit = data.totalQuestions || data.total || 0;
    setTotal(limit);
    setRemaining(limit - 1);
    setQuestionNumber(data.questionNumber || 1);
    setScore(0);
    setElapsedSeconds(0);
    setStartedAt(Date.now());
    setQuestionStartedAt(Date.now());
    setReviewMode(false);
    setFeedback(null);
    setPendingQuestion(null);
    setPendingMeta(null);
    setSessionXp(null);
    setAchievementsUnlocked([]);
  };

  // Assigned test: use session endpoints (unchanged)
  const loadAssigned = async () => {
    if (!assignmentId) return;
    try {
      const data = await api<any>("/api/sessions/start", {
        method: "POST",
        body: JSON.stringify({ assignment_id: assignmentId }),
      });
      const tid = data?.test_id || data?.testId;
      if (tid) setResolvedTestId(String(tid));
      const q = data.question;
      if (!q) throw new Error("No question returned");
      const first = { id: q.id || q.question, question: q.question, options: q.options || [], difficulty: q.difficulty };
      setQuestions([first]);
      setCurrent(first);
      const limit = data.totalQuestions || data.total || 0;
      setTotal(limit);
      setAssignedLimit(limit);
    setAssignedQuestionNumber(data.questionNumber || 1);
    setElapsedSeconds(0);
    setStartedAt(Date.now());
    setQuestionStartedAt(Date.now());
    setReviewMode(false);
    setFeedback(null);
    setPendingQuestion(null);
    setPendingMeta(null);
    setSessionXp(null);
    setAchievementsUnlocked([]);
  } catch (err: any) {
      showToast(err?.message || "Failed to start test", "error");
      onExit();
    } finally {
      setLoading(false);
    }
  };

  const loadPractice = async () => {
    try {
      setScore(0);
      await startPractice();
    } catch (err: any) {
      showToast(err?.message || "Failed to load quiz", "error");
      onExit();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    api<{ user: any }>("/api/auth/me")
      .then((res) => setUserId(res?.user?.id || null))
      .catch(() => setUserId(null));
    if (mode === "assigned") {
      loadAssigned();
    } else {
      loadPractice();
    }
  }, [mode, assignmentId, testId]);

  useEffect(() => {
    if (phase !== "quiz" || startedAt == null) return;
    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [phase, startedAt]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const handleAnswer = (qid: string, val: string) => {
    setAnswers((prev) => ({ ...prev, [qid]: val }));
  };

  const buildFeedback = (payload: any, currentQuestion: Question, studentAnswer: string) => {
    const evaluation = payload?.evaluation || {};
    const mastery = payload?.mastery || {};
    const metrics = evaluation?.metrics || {};
    const isCorrect = Boolean(metrics.is_correct);
    const confidence = metrics.confidence != null ? Math.round(metrics.confidence * 100) : null;
    const timeRatio = metrics.time_ratio != null ? Number(metrics.time_ratio) : null;
    const similarity = metrics.text_similarity != null ? Number(metrics.text_similarity) : null;
    const correctAnswer = evaluation.correct_answer || currentQuestion.correct_answer || "";
    const masteryScore = mastery.mastery_score != null ? Number(mastery.mastery_score) : null;
    const evidence = Array.isArray(payload?.evidence)
      ? payload.evidence
          .map((e: any) => String(e || "").trim())
          .filter((e: string) => e.length > 0)
      : [];

    let summary = isCorrect ? "Correct answer." : "Incorrect answer.";
    if (!isCorrect && similarity != null && similarity < 0.4) {
      summary = "Your answer did not match the expected concept.";
    }
    if (timeRatio != null && timeRatio < 0.7) {
      summary += " You answered very quickly.";
    } else if (timeRatio != null && timeRatio > 1.4) {
      summary += " You took longer than expected.";
    }

    let impact = "Steady";
    if (masteryScore != null) {
      if (masteryScore >= 80) impact = "Boosted";
      else if (masteryScore < 60) impact = "Needs Review";
    }

    return {
      isCorrect,
      summary,
      studentAnswer,
      correctAnswer,
      evidence,
      masteryScore,
      confidence,
      impact,
    };
  };

  const advanceToNextQuestion = () => {
    if (!pendingQuestion) return;
    setCurrent(pendingQuestion);
    setQuestionStartedAt(Date.now());
    setAnswers({});
    setReviewMode(false);
    setPendingQuestion(null);
    if (pendingMeta) {
      if (mode === "practice") {
        if (pendingMeta.remaining != null) setRemaining(pendingMeta.remaining);
        if (pendingMeta.limit != null) setTotal(pendingMeta.limit);
        if (typeof pendingMeta.answered === "number") {
          setQuestionNumber(pendingMeta.answered + 1);
        }
      } else {
        if (pendingMeta.limit != null) setAssignedLimit(pendingMeta.limit);
        if (typeof pendingMeta.answered === "number") {
          setAssignedQuestionNumber(pendingMeta.answered + 1);
        } else {
          setAssignedQuestionNumber((prev) => prev + 1);
        }
      }
    }
    setPendingMeta(null);
  };

  const renderFeedbackPanel = (showNext: boolean) => {
    if (!feedback) return null;
    return (
      <Card>
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-xs text-[#9CA3AF] mb-1">Answer Feedback</p>
            <h3 className={`text-xl ${feedback.isCorrect ? "text-[#22C55E]" : "text-[#EF4444]"}`}>
              {feedback.isCorrect ? "Correct" : "Needs Review"}
            </h3>
          </div>
          <Chip variant={feedback.isCorrect ? "success" : "warning"} size="sm">
            {feedback.impact}
          </Chip>
        </div>
        <p className="text-sm text-[#475569] mb-3">{feedback.summary}</p>
        <div className="grid md:grid-cols-2 gap-4 mb-4">
          <div className="glass rounded-xl p-3">
            <p className="text-xs text-[#9CA3AF] mb-1">Your answer</p>
            <p className="text-sm">{feedback.studentAnswer || "--"}</p>
          </div>
          <div className="glass rounded-xl p-3">
            <p className="text-xs text-[#9CA3AF] mb-1">Correct answer</p>
            <p className="text-sm">{feedback.correctAnswer || "--"}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          {feedback.masteryScore != null && (
            <Chip variant="info" size="sm">
              Mastery {feedback.masteryScore}
            </Chip>
          )}
          {feedback.confidence != null && (
            <Chip variant="secondary" size="sm">
              Confidence {feedback.confidence}%
            </Chip>
          )}
        </div>
        {mode === "practice" && Array.isArray(feedback.evidence) && feedback.evidence.length > 0 && (
          <details className="glass rounded-xl p-3 mb-4">
            <summary className="text-xs text-[#4169E1] cursor-pointer select-none">Show evidence from your material</summary>
            <div className="mt-3 space-y-2 max-h-48 overflow-auto pr-1">
              {feedback.evidence.map((e: string, idx: number) => (
                <p key={idx} className="text-sm text-[#475569] border-l-2 border-[#E5E7EB] pl-3">
                  {e}
                </p>
              ))}
            </div>
          </details>
        )}
        {pendingQuestion && (
          <div className="glass rounded-xl p-3 mb-4">
            <p className="text-xs text-[#9CA3AF] mb-1">Next recommended question</p>
            <p className="text-sm">{pendingQuestion.question}</p>
          </div>
        )}
        {showNext && (
          <Button variant="primary" onClick={advanceToNextQuestion}>
            Next Question
          </Button>
        )}
      </Card>
    );
  };

  const handleSubmitPractice = async () => {
    if (!current || !testId) return;
    if (submitting) return;

    const selected = (answers[current.id] || "").trim();
    if (Array.isArray(current.options) && current.options.length > 0 && !selected) {
      showToast("Select an answer first", "error");
      return;
    }
    try {
      setSubmitting(true);
      const timeTakenSeconds = questionStartedAt ? (Date.now() - questionStartedAt) / 1000 : undefined;
      const res = await api<any>("/api/practice/answer", {
        method: "POST",
        body: JSON.stringify({
          test_id: testId,
          student_answer: answers[current.id] || "",
          time_taken_seconds: timeTakenSeconds,
        }),
      });
      setDebugPayload({ mode: "practice-answer", data: res });
      setSessionXp({
        xp_awarded: res?.xp_awarded || 0,
        xp_total: res?.xp_total,
        level: res?.level,
        bonus_xp: res?.bonus_xp || 0,
      });
      if (Array.isArray(res?.achievements_unlocked) && res.achievements_unlocked.length > 0) {
        setAchievementsUnlocked(res.achievements_unlocked);
      }
      setScore(res.score ?? score ?? 0);
      setFeedback(buildFeedback(res, current, selected));
      if (res.done || !res.next_question) {
        setRemaining(0);
        setTotal(res.limit || total);
        setReviewMode(false);
        setPhase("completion");
        return;
      }
      if (res.next_question) {
        const q = res.next_question;
        setPendingQuestion({
          id: q.id || q.question,
          question: q.question,
          options: q.options || [],
          correct_answer: q.correct_answer,
          section: q.section,
          difficulty: q.difficulty,
        });
        setPendingMeta({ answered: res.answered, remaining: res.remaining, limit: res.limit });
        setReviewMode(true);
      }
    } catch (err: any) {
      showToast(err?.message || "Failed to submit answer", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitAssigned = async () => {
    if (!assignmentId || !current) return;
    if (submitting) return;

    const selected = (answers[current.id] || "").trim();
    if (Array.isArray(current.options) && current.options.length > 0 && !selected) {
      showToast("Select an answer first", "error");
      return;
    }
    try {
      setSubmitting(true);
      const timeTakenSeconds = questionStartedAt ? (Date.now() - questionStartedAt) / 1000 : undefined;
      const res = await api<any>("/api/sessions/submit-answer", {
        method: "POST",
        body: JSON.stringify({
          assignment_id: assignmentId,
          student_answer: answers[current.id] || "",
          time_taken_seconds: timeTakenSeconds,
        }),
      });

      if (res.done) {
        setScore(res.score || 0);
        if (res.limit != null) setTotal(res.limit);
        const tid = res?.test_id || res?.testId;
        if (tid) setResolvedTestId(String(tid));
        setReviewMode(false);
        setFeedback(buildFeedback(res, current, selected));
        setPhase("completion");
        setSessionXp({
          xp_awarded: res?.xp_awarded || 0,
          xp_total: res?.xp_total,
          level: res?.level,
          bonus_xp: res?.bonus_xp || 0,
        });
        if (Array.isArray(res?.achievements_unlocked) && res.achievements_unlocked.length > 0) {
          setAchievementsUnlocked(res.achievements_unlocked);
        }
        return;
      }
      if (res.next_question) {
        setFeedback(buildFeedback(res, current, selected));
        setSessionXp({
          xp_awarded: res?.xp_awarded || 0,
          xp_total: res?.xp_total,
          level: res?.level,
          bonus_xp: res?.bonus_xp || 0,
        });
        if (Array.isArray(res?.achievements_unlocked) && res.achievements_unlocked.length > 0) {
          setAchievementsUnlocked(res.achievements_unlocked);
        }
        const q = res.next_question;
        const nq = {
          id: q.id || q.question,
          question: q.question,
          options: q.options || [],
          correct_answer: q.correct_answer,
          section: q.section,
          difficulty: q.difficulty,
        };
        setPendingQuestion(nq);
        setPendingMeta({ answered: res.answered, limit: res.limit });
        setReviewMode(true);
      }
    } catch (err: any) {
      showToast(err?.message || "Failed to submit", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-sm text-[#9CA3AF]">Loading quiz...</div>
      </div>
    );
  }

  if (phase === "completion") {
    const effectiveTestId = resolvedTestId || testId || null;
    return (
      <div className="min-h-screen flex items-center justify-center p-8 relative overflow-hidden">
      <div className="glass rounded-2xl p-6 w-full max-w-3xl">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-[#9CA3AF] mb-1">Quiz complete</p>
              <h3 className="text-3xl font-semibold">Great job!</h3>
            </div>
            <Button variant="tertiary" icon={X} onClick={onExit}>Close</Button>
          </div>
          <div className="mt-6 grid grid-cols-2 gap-4">
            <Card>
              <p className="text-sm text-[#9CA3AF] mb-1">Score</p>
              <p className="text-2xl">{score ?? 0} / {total || "?"}</p>
            </Card>
            <Card>
              <p className="text-sm text-[#9CA3AF] mb-1">Time</p>
              <p className="text-2xl">{formatTime(elapsedSeconds)}</p>
            </Card>
          </div>
          {sessionXp && (
            <div className="mt-6 glass rounded-xl p-4 bg-[#F9FAFB]">
              <p className="text-sm text-[#9CA3AF]">XP Earned</p>
              <p className="text-2xl font-semibold">{sessionXp.xp_awarded + (sessionXp.bonus_xp || 0)} XP</p>
              {sessionXp.bonus_xp ? (
                <p className="text-xs text-[#22C55E]">
                  Bonus for mastery improvement: +{sessionXp.bonus_xp} XP
                </p>
              ) : null}
              <p className="text-xs text-[#9CA3AF] mt-2">
                Total XP: {sessionXp.xp_total ?? "--"} (Level {sessionXp.level ?? "--"})
              </p>
            </div>
          )}
          {achievementsUnlocked.length > 0 && (
            <div className="mt-4 glass rounded-xl p-3 bg-[#FFF8F1]">
              <p className="text-xs text-[#EA580C] mb-2">New badges unlocked</p>
              <div className="flex flex-wrap gap-2">
                {achievementsUnlocked.map((ach) => (
                  <span key={ach} className="px-3 py-1 rounded-full bg-[#FEF3C7] text-[#92400E] text-xs">
                    {ach}
                  </span>
                ))}
              </div>
            </div>
          )}
          {feedback && (
            <div className="mt-6">
              {renderFeedbackPanel(false)}
            </div>
          )}
          <div className="mt-6 flex gap-3">
            <Button
              variant="primary"
              icon={Trophy}
              onClick={() => {
                if (!effectiveTestId) {
                  showToast("Missing test id", "error");
                  return;
                }
                const href = userId
                  ? `/api/tests/${effectiveTestId}/mastery-report?student_id=${userId}&format=pdf`
                  : `/api/tests/${effectiveTestId}/quiz?format=pdf`;
                window.open(href, "_blank");
              }}
            >
              Download Report
            </Button>
            <Button
              variant="secondary"
              icon={Download}
              onClick={() => {
                if (!effectiveTestId) {
                  showToast("Missing test id", "error");
                  return;
                }
                window.open(`/api/tests/${effectiveTestId}/quiz?format=pdf`, "_blank");
              }}
            >
              Download Quiz
            </Button>
            <Button variant="tertiary" onClick={onExit}>Back to Dashboard</Button>
          </div>
        </div>
      </div>
    );
  }

  if (!current) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-sm text-[#9CA3AF]">No question available.</div>
      </div>
    );
  }

  if (mode === "assigned") {
    const progress = assignedLimit ? Math.round((assignedQuestionNumber / assignedLimit) * 100) : 0;
    return (
      <div className="min-h-screen flex flex-col gap-4 p-6 bg-[#F5F7FB]">
        <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Clock size={18} className="text-[#4169E1]" />
          <span className="text-sm text-[#475569]">Time: {formatTime(elapsedSeconds)}</span>
          </div>
          <Button variant="tertiary" icon={X} onClick={onExit}>Exit</Button>
        </div>

        {reviewMode && renderFeedbackPanel(true)}

        {!reviewMode && (
          <Card>
            <div className="flex items-start justify-between mb-4">
              <div>
                <p className="text-xs uppercase text-[#9CA3AF] mb-1">Question</p>
                {current.difficulty ? (
                  <p className="text-xs text-[#4169E1] mb-1">Difficulty: {current.difficulty}</p>
                ) : null}
                <h3 className="text-xl">{current.question}</h3>
              </div>
            </div>
            <div className="space-y-3">
              {current.options?.map((opt, idx) => {
                const selected = answers[current.id] === opt;
                return (
                  <label
                    key={idx}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer ${selected ? "border-[#4169E1] bg-[#E3EBFF]" : "border-[#E5E7EB]"}`}
                  >
                    <input
                      type="radio"
                      name={current.id}
                      checked={selected}
                      onChange={() => handleAnswer(current.id, opt)}
                      disabled={reviewMode}
                    />
                    <span>{opt}</span>
                  </label>
                );
              })}
            </div>
            <div className="mt-4 flex justify-between">
              <Button variant="primary" onClick={handleSubmitAssigned} disabled={submitting || reviewMode}>
                Submit
              </Button>
              <ProgressBar progress={progress} />
            </div>
          </Card>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col gap-4 p-6 bg-[#F5F7FB]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Clock size={18} className="text-[#4169E1]" />
          <span className="text-sm text-[#475569]">
            Remaining: {remaining} • Time: {formatTime(elapsedSeconds)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {debugPayload && (
            <Button variant="tertiary" size="sm" onClick={() => setShowDebug((v) => !v)}>
              {showDebug ? "Hide Debug" : "Show Debug"}
            </Button>
          )}
          <Button variant="tertiary" icon={X} onClick={onExit}>Exit</Button>
        </div>
      </div>

      {showDebug && debugPayload && (
        <div className="rounded-xl bg-[#0f172a] text-white/80 p-3 text-xs">
          <div className="mb-2 font-semibold">Debug payload</div>
          <pre className="whitespace-pre-wrap break-words">{JSON.stringify(debugPayload, null, 2)}</pre>
        </div>
      )}

      {reviewMode && renderFeedbackPanel(true)}

      {!reviewMode && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs uppercase text-[#9CA3AF] mb-1">Practice Quiz</p>
              <h3 className="text-xl">Question {questionNumber} / {total || "?"}</h3>
            </div>
            <div className="w-40">
              <ProgressBar progress={total ? Math.round((questionNumber / total) * 100) : 0} />
            </div>
          </div>

          <div className="rounded-xl border border-[#E5E7EB] p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs uppercase text-[#9CA3AF]">{current.section || "Quiz"}</div>
              {current.difficulty ? <div className="text-xs text-[#4169E1]">{current.difficulty}</div> : null}
            </div>
            <div className="font-medium">{current.question}</div>
            {Array.isArray(current.options) && current.options.length > 0 ? (
              current.options.map((opt, idx) => {
                const selected = answers[current.id] === opt;
                return (
                  <label
                    key={idx}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer ${selected ? "border-[#4169E1] bg-[#E3EBFF]" : "border-[#E5E7EB]"}`}
                  >
                    <input
                      type="radio"
                      name={current.id}
                      checked={selected}
                      onChange={() => handleAnswer(current.id, opt)}
                      disabled={reviewMode}
                    />
                    <span>{opt}</span>
                  </label>
                );
              })
            ) : (
              <input
                className="w-full rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm"
                value={answers[current.id] || ""}
                onChange={(e) => handleAnswer(current.id, e.target.value)}
                placeholder="Your answer"
                disabled={reviewMode}
              />
            )}
          </div>
          <div className="mt-4 flex justify-end">
            <Button variant="primary" onClick={handleSubmitPractice} disabled={submitting || reviewMode}>
              {remaining <= 0 ? "Submit" : "Next"}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
