import { useEffect, useMemo, useState } from "react";
import { Upload, Play, Download, Sparkles, AlertTriangle, Wand2 } from "lucide-react";
import { Hero } from "../Hero";
import { Card } from "../Card";
import { Button } from "../Button";
import { Input, Select } from "../Input";
import { Modal } from "../Modal";
import { StatusChip } from "../Chip";
import { useToast } from "../Toast";
import { motion } from "motion/react";
import { api } from "../../utils/api";
import { Stepper } from "../ProgressBar";

interface PracticeProps {
  onStartPractice: (practiceId: string) => void;
}

export function Practice({ onStartPractice }: PracticeProps) {
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const { showToast } = useToast();

  const [practices, setPractices] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [formData, setFormData] = useState({
    file: null as File | null,
    title: "",
    apiKey: "",
    model: "llama-3.3-70b",
    questionLimit: "20",
    topics: "",
    difficulty: "mixed",
    duration: "10",
  });

  const [createStatus, setCreateStatus] = useState<"idle" | "creating" | "ready" | "failed">("idle");
  const [createdTestId, setCreatedTestId] = useState<string | null>(null);
  const [previewQuestions, setPreviewQuestions] = useState<any[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const models = [
    { value: "llama-3.3-70b", label: "Llama 3.3 70B (Recommended)" },
    { value: "llama-3.1-8b", label: "Llama 3.1 8B (Fast)" },
    { value: "mixtral-8x7b", label: "Mixtral 8x7B (Balanced)" },
  ];

  const difficultyOptions = [
    { value: "mixed", label: "Mixed" },
    { value: "easy", label: "Mostly Easy" },
    { value: "medium", label: "Balanced" },
    { value: "hard", label: "Challenge Mode" },
  ];

  const wizardSteps = ["Upload", "Goals", "Preview"];

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFormData({ ...formData, file: e.target.files[0] });
    }
  };

  const fetchPractices = async () => {
    try {
      const data = await api<{ tests: any[] }>("/api/tests/my-tests");
      const filtered = (data.tests || []).filter((t) => t.kind === "practice");
      const mapped = filtered.map((t) => ({
        id: t.id,
        title: t.title,
        status: t.status,
        questions: t.questionLimit || t.limit,
        createdAt: t.createdAt || t.created_at || "",
        error: t.error,
        ready: t.status === "ready",
      }));
      setPractices(mapped);
    } catch (err: any) {
      showToast(err?.message || "Failed to load practice tests", "error");
    }
  };

  const fetchHistory = async () => {
    try {
      const data = await api<{ sessions: any[] }>("/api/student/practice/history");
      setHistory(data.sessions || []);
    } catch {
      setHistory([]);
    }
  };

  const fetchOverview = async () => {
    try {
      const data = await api<any>("/api/student/overview");
      setOverview(data);
    } catch {
      setOverview(null);
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchPractices(), fetchHistory(), fetchOverview()]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const raw = localStorage.getItem("icodex.practice.prefill");
    if (!raw) return;
    try {
      const prefill = JSON.parse(raw);
      if (prefill?.topic) {
        setFormData((prev) => ({ ...prev, topics: prefill.topic }));
        setShowWizard(true);
        setWizardStep(1);
      }
    } catch {
      // ignore
    } finally {
      localStorage.removeItem("icodex.practice.prefill");
    }
  }, []);

  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const extractPreviewQuestions = (root: any): { question: string; options: string[]; context: string }[] => {
    const results: { question: string; options: string[]; context: string }[] = [];

    const walk = (node: any, trail: string[]) => {
      if (!node) return;
      if (Array.isArray(node)) {
        node.forEach((child) => walk(child, trail));
        return;
      }
      if (typeof node !== "object") return;

      const title = node.title || node.name;
      const nextTrail = title ? [...trail, String(title)] : trail;

      if (Array.isArray(node.questions)) {
        const context = nextTrail.filter(Boolean).join(" > ") || "General";
        node.questions.forEach((q: any) => {
          results.push({
            question: q.question || "",
            options: Array.isArray(q.options) ? q.options : [],
            context,
          });
        });
      }

      Object.entries(node).forEach(([key, value]) => {
        if (key === "questions") return;
        walk(value, nextTrail);
      });
    };

    walk(root, []);
    return results.slice(0, 3);
  };

  const resetWizard = () => {
    setWizardStep(0);
    setCreateStatus("idle");
    setCreatedTestId(null);
    setPreviewQuestions([]);
    setPreviewError(null);
    setFormData({
      file: null,
      title: "",
      apiKey: "",
      model: "llama-3.3-70b",
      questionLimit: "20",
      topics: "",
      difficulty: "mixed",
      duration: "10",
    });
  };

  const handleGenerate = async () => {
    if (!formData.file || !formData.title) {
      showToast("Please upload a PDF and title", "error");
      return;
    }
    try {
      setCreateStatus("creating");
      setPreviewError(null);
      const pdfBase64 = await fileToBase64(formData.file);
      const limit = Math.min(100, Math.max(1, parseInt(formData.questionLimit, 10) || 10));
      const payload = {
        title: formData.title,
        questionLimit: limit,
        pdfBase64,
        apiKey: formData.apiKey,
        model: formData.model,
        kind: "practice",
        comment: "Practice test",
        goals: {
          topics: formData.topics,
          difficulty: formData.difficulty,
          duration_minutes: formData.duration,
        },
      };
      const res = await api<any>("/api/tests", { method: "POST", body: JSON.stringify(payload) });
      setCreatedTestId(res?.test?.id || null);
      setWizardStep(2);
      fetchPractices();
    } catch (err: any) {
      setCreateStatus("failed");
      setPreviewError(err?.message || "Failed to generate quiz");
    }
  };

  useEffect(() => {
    if (createStatus !== "creating" || !createdTestId) return;
    let active = true;
    const interval = setInterval(async () => {
      try {
        const data = await api<{ tests: any[] }>("/api/tests/my-tests");
        const test = (data.tests || []).find((t) => t.id === createdTestId);
        if (!test) return;
        if (String(test.status).startsWith("failed")) {
          if (!active) return;
          setCreateStatus("failed");
          setPreviewError(test.error || "Generation failed");
          clearInterval(interval);
        }
        if (test.status === "ready") {
          const quiz = await api<any>(`/api/tests/${createdTestId}/quiz`);
          if (!active) return;
          setPreviewQuestions(extractPreviewQuestions(quiz));
          setCreateStatus("ready");
          clearInterval(interval);
        }
      } catch (err: any) {
        if (!active) return;
        setCreateStatus("failed");
        setPreviewError(err?.message || "Failed to fetch preview");
        clearInterval(interval);
      }
    }, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [createStatus, createdTestId]);

  const focusConcepts = useMemo(() => {
    const weak = overview?.mastery?.weak || [];
    return weak.slice(0, 3);
  }, [overview]);

  return (
    <div>
      <Hero
        title="Practice Studio"
        description="Upload your own materials and build a focused practice session."
        primaryAction={{
          label: "Create Practice Quiz",
          icon: Upload,
          onClick: () => {
            resetWizard();
            setShowWizard(true);
          },
        }}
      />

      <div className="glass rounded-2xl p-4 mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">AI Focus for You</p>
          <p className="text-xs text-[#9CA3AF]">Practice the concepts you need most.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {focusConcepts.length === 0 ? (
            <span className="text-xs text-[#9CA3AF]">No weak concepts yet</span>
          ) : (
            focusConcepts.map((c: any) => (
              <span key={c.concept} className="text-xs px-3 py-1 rounded-full bg-[#F97316]/10 text-[#F97316]">
                {c.concept}
              </span>
            ))
          )}
        </div>
      </div>

      <div className="grid gap-6">
        {loading && (
          <Card>
            <div className="animate-pulse space-y-4">
              <div className="h-4 w-1/3 rounded-full bg-[#E3EBFF]/60" />
              <div className="h-6 w-1/2 rounded-full bg-[#E3EBFF]/60" />
              <div className="grid md:grid-cols-2 gap-3">
                <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
                <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              </div>
            </div>
          </Card>
        )}
        {!loading && practices.length === 0 && (
          <Card>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h3 className="text-lg mb-1">No practice sessions yet</h3>
                <p className="text-sm text-[#9CA3AF]">
                  Upload a PDF to generate a personalized practice quiz.
                </p>
              </div>
              <Button variant="secondary" icon={Wand2} onClick={() => setShowWizard(true)}>
                Start Practice
              </Button>
            </div>
          </Card>
        )}
        {practices.map((practice, index) => (
          <motion.div
            key={practice.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card hover>
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-xl">{practice.title}</h3>
                    <StatusChip status={practice.status} />
                  </div>
                  <div className="flex items-center gap-6 text-sm text-[#9CA3AF]">
                    <span>{practice.questions} questions</span>
                    <span>Created: {practice.createdAt || "--"}</span>
                  </div>
                  {practice.status !== "ready" && practice.status !== "failed" && (
                    <div className="mt-2 text-sm text-[#F97316]">
                      Quiz not ready yet. Please check back soon.
                    </div>
                  )}
                  {practice.status === "failed" && practice.error && (
                    <div className="mt-2 text-sm text-[#EF4444] flex items-center gap-2">
                      <AlertTriangle size={14} />
                      <span>{practice.error}</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  {practice.status === "ready" && (
                    <>
                      <Button variant="primary" icon={Play} onClick={() => onStartPractice(practice.id)}>
                        Start Practice
                      </Button>
                      <Button variant="secondary" icon={Download} asChild>
                        <a href={`/api/tests/${practice.id}/quiz?format=pdf`} target="_blank" rel="noreferrer">
                          Download PDF
                        </a>
                      </Button>
                    </>
                  )}
                  {practice.status === "processing" && (
                    <div className="glass rounded-xl px-4 py-2 flex items-center gap-2">
                      <div className="w-2 h-2 bg-[#F97316] rounded-full animate-pulse" />
                      <span className="text-sm text-[#F97316]">Processing...</span>
                    </div>
                  )}
                  {practice.status === "failed" && (
                    <Button variant="secondary" icon={Sparkles} onClick={() => setShowWizard(true)}>
                      Retry
                    </Button>
                  )}
                  <Button
                    variant="tertiary"
                    onClick={async () => {
                      if (!window.confirm("Delete this practice quiz permanently? This cannot be undone.")) return;
                      try {
                        await api(`/api/tests/${practice.id}`, { method: "DELETE" });
                        showToast("Practice quiz deleted", "success");
                        fetchPractices();
                        fetchHistory();
                      } catch (err: any) {
                        showToast(err?.message || "Failed to delete practice quiz", "error");
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="mt-8">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Recent Practice Sessions</h3>
            <Button variant="tertiary" size="sm" onClick={fetchHistory}>
              Refresh
            </Button>
          </div>
          {history.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No completed practice sessions yet.</p>
          ) : (
            <div className="space-y-3">
              {history.map((session: any) => (
                <div key={session.test_id} className="glass rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold">{session.title}</p>
                      <p className="text-xs text-[#9CA3AF]">
                        {session.question_count} questions - {session.time_spent ?? "--"} mins
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                        {session.score ?? "--"}%
                      </p>
                      <p className="text-xs text-[#9CA3AF]">{session.completed_at || ""}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-3">
                    {(session.strengths || []).slice(0, 2).map((c: string) => (
                      <span key={c} className="text-xs px-3 py-1 rounded-full bg-[#22C55E]/10 text-[#16A34A]">
                        {c}
                      </span>
                    ))}
                    {(session.weaknesses || []).slice(0, 2).map((c: string) => (
                      <span key={c} className="text-xs px-3 py-1 rounded-full bg-[#F97316]/10 text-[#F97316]">
                        {c}
                      </span>
                    ))}
                  </div>
                  <div className="mt-3">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        if (session.weaknesses?.length) {
                          localStorage.setItem(
                            "icodex.practice.prefill",
                            JSON.stringify({ topic: session.weaknesses[0] }),
                          );
                        }
                        setShowWizard(true);
                        setWizardStep(1);
                      }}
                    >
                      Retry weak concepts
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        isOpen={showWizard}
        onClose={() => setShowWizard(false)}
        title="Create Practice Quiz"
        description="Build a focused session in three quick steps."
        footer={
          <>
            <Button variant="tertiary" onClick={() => setShowWizard(false)}>
              Cancel
            </Button>
            {wizardStep === 0 && (
              <Button variant="primary" onClick={() => setWizardStep(1)} disabled={!formData.file || !formData.title}>
                Next
              </Button>
            )}
            {wizardStep === 1 && (
              <Button variant="primary" icon={Sparkles} onClick={handleGenerate}>
                Generate Preview
              </Button>
            )}
            {wizardStep === 2 && createStatus === "ready" && createdTestId && (
              <Button variant="primary" icon={Play} onClick={() => onStartPractice(createdTestId)}>
                Start Practice
              </Button>
            )}
          </>
        }
      >
        <div className="space-y-6">
          <Stepper steps={wizardSteps} currentStep={wizardStep} />

          {wizardStep === 0 && (
            <div className="space-y-4">
              <Input
                label="Quiz Title *"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="e.g., Calculus Practice"
              />

              <div>
                <label className="block mb-2 text-sm text-[#475569]">Upload PDF *</label>
                <div className="glass rounded-xl p-6 border-2 border-dashed border-[#4169E1]/30 hover:border-[#4169E1] transition-colors cursor-pointer">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={handleFileChange}
                    className="hidden"
                    id="practice-file-upload"
                  />
                  <label htmlFor="practice-file-upload" className="cursor-pointer flex flex-col items-center">
                    <Upload size={32} className="text-[#4169E1] mb-2" />
                    {formData.file ? (
                      <p className="text-[#4169E1] text-sm">{formData.file.name}</p>
                    ) : (
                      <>
                        <p className="text-sm mb-1">Click to upload PDF</p>
                        <p className="text-xs text-[#9CA3AF]">Max 50MB</p>
                      </>
                    )}
                  </label>
                </div>
              </div>
            </div>
          )}

          {wizardStep === 1 && (
            <div className="space-y-4">
              <Input
                label="Focus Topics"
                value={formData.topics}
                onChange={(e) => setFormData({ ...formData, topics: e.target.value })}
                placeholder="e.g., Loops, Functions"
                helperText="Comma-separated topics to emphasize."
              />
              <Select
                label="Difficulty"
                options={difficultyOptions}
                value={formData.difficulty}
                onChange={(e) => setFormData({ ...formData, difficulty: e.target.value })}
              />
              <Input
                label="Question Limit"
                type="number"
                placeholder="20"
                value={formData.questionLimit}
                onChange={(e) => setFormData({ ...formData, questionLimit: e.target.value })}
                min={1}
                max={100}
              />
              <Input
                label="Session Length (mins)"
                type="number"
                placeholder="10"
                value={formData.duration}
                onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
                min={5}
                max={60}
              />
              <Input
                label="Cerebras API Key (optional)"
                type="password"
                placeholder="csk-..."
                value={formData.apiKey}
                onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
                helperText="Optional if the server has CEREBRAS_API_KEY set. Used only for generation."
              />
              <Select
                label="AI Model"
                options={models}
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              />
            </div>
          )}

          {wizardStep === 2 && (
            <div className="space-y-4">
              {createStatus === "creating" && (
                <div className="glass rounded-xl p-4">
                  <p className="text-sm text-[#9CA3AF]">Generating your quiz preview...</p>
                </div>
              )}
              {createStatus === "failed" && (
                <div className="glass rounded-xl p-4 bg-[#FEF2F2]">
                  <p className="text-sm text-[#EF4444]">{previewError || "Preview failed"}</p>
                </div>
              )}
              {createStatus === "ready" && (
                <>
                  <div className="glass rounded-xl p-4 bg-[#E3EBFF]/30">
                    <p className="text-sm text-[#9CA3AF] mb-1">Preview</p>
                    <p className="text-sm">Here are the first questions your quiz will include.</p>
                  </div>
                  {previewQuestions.length === 0 ? (
                    <p className="text-sm text-[#9CA3AF]">No questions found in quiz preview.</p>
                  ) : (
                    previewQuestions.map((q, idx) => (
                      <div key={`${q.context}-${idx}`} className="glass rounded-xl p-4">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs text-[#9CA3AF]">{q.context}</p>
                          <span className="text-xs text-[#9CA3AF]">Q{idx + 1}</span>
                        </div>
                        <p className="text-sm text-[#0F172A] mb-2">{q.question}</p>
                        {q.options && q.options.length > 0 && (
                          <ul className="list-disc ml-5 text-sm text-[#475569] space-y-1">
                            {q.options.map((opt: string, i: number) => (
                              <li key={i}>{opt}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
