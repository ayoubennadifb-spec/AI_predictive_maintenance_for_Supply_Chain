import { useState, useEffect } from "react";
import { Upload, Sparkles, Download, Eye, Users } from "lucide-react";
import { Hero } from "../Hero";
import { Card } from "../Card";
import { Button } from "../Button";
import { Input, TextArea, Select } from "../Input";
import { Modal } from "../Modal";
import { Stepper, ProgressBar } from "../ProgressBar";
import { useToast } from "../Toast";
import { motion } from "motion/react";
import { api } from "../../utils/api";

export function QuizStudio() {
  const DRAFT_KEY = "icodex.quizStudioDraft.v1";
  const [step, setStep] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState<string>("");
  const [errorText, setErrorText] = useState<string>("");
  const { showToast } = useToast();

  const [formData, setFormData] = useState({
    file: null as File | null,
    apiKey: "",
    model: "llama-3.3-70b",
    questionLimit: "30",
    comment: "",
    conceptsInclude: "",
    conceptsExclude: "",
    difficultyEasy: "30",
    difficultyMedium: "50",
    difficultyHard: "20",
    bloom: {
      understand: true,
      apply: true,
      analyze: false,
      evaluate: false,
      create: false,
    },
  });

  const [logs, setLogs] = useState<string[]>([]);
  const [lastTestId, setLastTestId] = useState<string | null>(null);
  const [lastDownloads, setLastDownloads] = useState<{ pdf?: string; json?: string }>({});
  const [polling, setPolling] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewQuiz, setPreviewQuiz] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [teacherCanAssign, setTeacherCanAssign] = useState(false);
  const [teacherClasses, setTeacherClasses] = useState<{ id: string; name: string }[]>([]);
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [assignClassId, setAssignClassId] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [assignedClasses, setAssignedClasses] = useState<{ class_id: string | null; class_name: string }[]>([]);
  const [assignedLoading, setAssignedLoading] = useState(false);

  const models = [
    { value: "llama-3.3-70b", label: "Llama 3.3 70B (Recommended)" },
    { value: "llama-3.1-8b", label: "Llama 3.1 8B (Fast)" },
    { value: "mixtral-8x7b", label: "Mixtral 8x7B (Balanced)" },
  ];

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFormData({ ...formData, file: e.target.files[0] });
    }
  };

  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  useEffect(() => {
    // Load a local draft (no API key / no file contents stored)
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const draft = JSON.parse(raw);
        setFormData((prev) => ({
          ...prev,
          model: draft?.model || prev.model,
          questionLimit: draft?.questionLimit || prev.questionLimit,
          comment: draft?.comment || prev.comment,
          conceptsInclude: draft?.conceptsInclude || "",
          conceptsExclude: draft?.conceptsExclude || "",
          difficultyEasy: draft?.difficultyEasy || prev.difficultyEasy,
          difficultyMedium: draft?.difficultyMedium || prev.difficultyMedium,
          difficultyHard: draft?.difficultyHard || prev.difficultyHard,
        }));
        showToast("Draft loaded (please re-select your PDF before generating)", "info");
      }
    } catch {
      // ignore
    }

    // Load admin-config + my classes so we can optionally assign after generation
    (async () => {
      try {
        const me = await api<{ user: any }>("/api/auth/me");
        const cfg = await api<{ config: any }>("/api/config").catch(() => ({ config: { teacher_can_assign: false } }));
        setTeacherCanAssign(!!cfg?.config?.teacher_can_assign);
        const classesRes = await api<{ classes: any[] }>("/api/classes").catch(() => ({ classes: [] }));
        const my = (classesRes.classes || [])
          .filter((c: any) => Array.isArray(c.teachers) && c.teachers.includes(me.user?.id))
          .map((c: any) => ({ id: c.id, name: c.name }));
        setTeacherClasses(my);
      } catch {
        setTeacherCanAssign(false);
        setTeacherClasses([]);
      }
    })();
  }, [showToast]);

  const handleSaveDraft = () => {
    try {
      const draft = {
        model: formData.model,
        questionLimit: formData.questionLimit,
        comment: formData.comment,
        conceptsInclude: formData.conceptsInclude,
        conceptsExclude: formData.conceptsExclude,
        difficultyEasy: formData.difficultyEasy,
        difficultyMedium: formData.difficultyMedium,
        difficultyHard: formData.difficultyHard,
        fileName: formData.file?.name || "",
        savedAt: new Date().toISOString(),
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      showToast("Draft saved (API key is never stored)", "success");
    } catch {
      showToast("Failed to save draft", "error");
    }
  };

  const handleUpload = async () => {
    if (!formData.file) {
      showToast("Please upload a PDF", "error");
      return;
    }

    setProcessing(true);
    setStep(1);
    setLogs([]);
    setProgress(15);
    setStatusText("Starting pipeline...");
    setErrorText("");

    try {
      const pdfBase64 = await fileToBase64(formData.file);
      const limit = Math.min(100, Math.max(1, parseInt(formData.questionLimit, 10) || 10));
      const payload = {
        title: formData.file.name,
        comment: formData.comment,
        questionLimit: limit,
        pdfBase64,
        apiKey: formData.apiKey,
        model: formData.model,
        kind: "class_test",
        goals: {
          concepts_include: formData.conceptsInclude,
          concepts_exclude: formData.conceptsExclude,
          target_difficulty: {
            easy: Number(formData.difficultyEasy) || 0,
            medium: Number(formData.difficultyMedium) || 0,
            hard: Number(formData.difficultyHard) || 0,
          },
          target_bloom: Object.entries(formData.bloom)
            .filter(([, val]) => val)
            .map(([key]) => key),
        },
      };

      const res = await api<{ test: any }>("/api/tests", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const test = res?.test;
      if (test?.id) setLastTestId(test.id);
      setStatusText(test?.status || "processing");
      const pdfPath = test?.quizPdfPath || test?.paths?.quiz_pdf || test?.pdfPath || test?.quiz_pdf;
      const jsonPath = test?.quizJsonPath || test?.paths?.quiz_json || test?.jsonPath || test?.quiz_json;
      // Keep raw paths only for debugging if needed; UI uses API endpoints.
      setLastDownloads({ pdf: pdfPath, json: jsonPath });

      setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] Upload started...`]);
      setProgress(45);

      setTimeout(() => {
        setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] Processing quiz...`]);
        setProgress(75);
      }, 1500);

      // Start polling backend for the real status/output
      setPolling(true);
    } catch (err: any) {
      showToast(err?.message || "Failed to generate quiz", "error");
      setProcessing(false);
      setStep(0);
      setStatusText("");
      setErrorText(err?.message || "");
    }
  };

  // Poll the backend for the test status/paths until ready/failed/pending_review
  useEffect(() => {
    if (!polling || !lastTestId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api<{ tests: any[] }>("/api/tests/my-tests");
        const found = (data.tests || []).find((t) => t.id === lastTestId);
        if (!found) return;
        const status = (found.status || "").toLowerCase();
        const isFailed = status.startsWith("failed");
        const isReady = status === "ready" || status === "pending_review";
        setStatusText(found.status || status);
        // Keep raw paths only for debugging if needed; UI uses API endpoints.
        setLastDownloads({
          pdf: found.quizPdfPath || found.paths?.quiz_pdf,
          json: found.quizJsonPath || found.paths?.quiz_json,
        });
        if (isFailed) {
          setErrorText(found.error || found.status || "Generation failed");
          setProcessing(false);
          setStep(0);
          setPolling(false);
          showToast("Quiz generation failed. Please retry in a few seconds.", "error");
          return;
        }
        if (isReady) {
          setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] Quiz generation complete`] );
          setProgress(100);
          setStep(2);
          setProcessing(false);
          setPolling(false);
          showToast(status === "pending_review" ? "Quiz generated; waiting admin approval." : "Quiz generated successfully!", "success");
          return;
        }
      } catch (err: any) {
        setErrorText(err?.message || "Polling failed");
      }
      if (!cancelled) {
        setTimeout(poll, 3000);
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [polling, lastTestId, showToast]);

  const steps = ["Upload & Configure", "Processing", "Ready"];

  // Always download via backend API, never direct filesystem paths.
  const pdfHref = lastTestId ? `/api/tests/${lastTestId}/quiz?format=pdf` : "#";
  const ready = !processing && step === 2;
  const canAssignNow =
    !!lastTestId && ready && teacherCanAssign && teacherClasses.length > 0 && !statusText?.toLowerCase().includes("pending");

  const loadAssignedClasses = async (testId: string) => {
    try {
      setAssignedLoading(true);
      const res = await api<{ classes: any[] }>(`/api/tests/${testId}/assigned-classes`);
      const normalized = (res.classes || []).map((c: any) => ({
        class_id: c.class_id ?? null,
        class_name: c.class_name || c.name || "Class",
      }));
      setAssignedClasses(normalized);
    } catch {
      setAssignedClasses([]);
    } finally {
      setAssignedLoading(false);
    }
  };

  const openPreview = async () => {
    if (!lastTestId) return;
    try {
      setPreviewLoading(true);
      const quiz = await api<any>(`/api/tests/${lastTestId}/quiz`);
      setPreviewQuiz(quiz);
      setShowPreviewModal(true);
    } catch (err: any) {
      showToast(err?.message || "Failed to load quiz preview", "error");
    } finally {
      setPreviewLoading(false);
    }
  };

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
        const context = nextTrail.filter(Boolean).join(" › ") || "General";
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
    return results;
  };

  return (
    <div>
      <Hero
        title="Quiz Studio"
        description="Upload your course materials, steer AI coverage, and generate adaptive quizzes."
        badge={{ label: processing ? "Processing" : "Ready", variant: processing ? "warning" : "success" }}
      />

      <div className="mb-8">
        <Stepper steps={steps} currentStep={step} />
      </div>

      {step === 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <h3 className="text-xl mb-6">Upload Configuration</h3>
            <div className="space-y-6">
              <div>
                <label className="block mb-2 text-sm text-[#475569]">Course PDF *</label>
                <div className="glass rounded-xl p-8 border-2 border-dashed border-[#4169E1]/30 hover:border-[#4169E1] transition-colors cursor-pointer">
                  <input type="file" accept=".pdf" onChange={handleFileChange} className="hidden" id="file-upload" />
                  <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
                    <Upload size={40} className="text-[#4169E1] mb-3" />
                    {formData.file ? (
                      <p className="text-[#4169E1]">{formData.file.name}</p>
                    ) : (
                      <>
                        <p className="mb-1">Click to upload PDF</p>
                        <p className="text-sm text-[#9CA3AF]">Maximum file size: 50MB</p>
                      </>
                    )}
                  </label>
                </div>
              </div>

              <Input
                label="Cerebras API Key (optional)"
                type="password"
                placeholder="csk-..."
                value={formData.apiKey}
                onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
                helperText="Optional if the server has CEREBRAS_API_KEY set. Used only for generation; not stored in app state."
              />

              <Select
                label="AI Model *"
                options={models}
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                helperText="Choose the model that best fits your needs"
              />

              <Input
                label="Question Limit *"
                type="number"
                placeholder="30"
                value={formData.questionLimit}
                onChange={(e) => setFormData({ ...formData, questionLimit: e.target.value })}
                min={1}
                max={100}
                helperText="Questions used in this test (max 100). A 100-question bank is generated and this sets how many are used."
              />

              <Input
                label="Concepts to focus (comma separated)"
                placeholder="Loops, Recursion"
                value={formData.conceptsInclude}
                onChange={(e) => setFormData({ ...formData, conceptsInclude: e.target.value })}
                helperText="AI will emphasize these concepts."
              />
              <Input
                label="Concepts to exclude (optional)"
                placeholder="Intro material, appendices"
                value={formData.conceptsExclude}
                onChange={(e) => setFormData({ ...formData, conceptsExclude: e.target.value })}
              />
              <div className="grid md:grid-cols-3 gap-3">
                <Input
                  label="Easy %"
                  type="number"
                  value={formData.difficultyEasy}
                  onChange={(e) => setFormData({ ...formData, difficultyEasy: e.target.value })}
                />
                <Input
                  label="Medium %"
                  type="number"
                  value={formData.difficultyMedium}
                  onChange={(e) => setFormData({ ...formData, difficultyMedium: e.target.value })}
                />
                <Input
                  label="Hard %"
                  type="number"
                  value={formData.difficultyHard}
                  onChange={(e) => setFormData({ ...formData, difficultyHard: e.target.value })}
                />
              </div>
              <div>
                <p className="text-sm text-[#475569] mb-2">Target Bloom Levels</p>
                <div className="flex flex-wrap gap-3 text-sm">
                  {["understand", "apply", "analyze", "evaluate", "create"].map((level) => (
                    <label key={level} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={formData.bloom[level as keyof typeof formData.bloom]}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            bloom: { ...prev.bloom, [level]: e.target.checked },
                          }))
                        }
                      />
                      <span className="capitalize">{level}</span>
                    </label>
                  ))}
                </div>
              </div>

              <TextArea
                label="Comment / Notes (Optional)"
                placeholder="Add any special instructions or notes about this test..."
                rows={4}
                value={formData.comment}
                onChange={(e) => setFormData({ ...formData, comment: e.target.value })}
              />

              <div className="flex gap-3 pt-4">
              <Button
                variant="primary"
                icon={Sparkles}
                onClick={handleUpload}
                disabled={!formData.file}
              >
                Generate Quiz
              </Button>
              <Button variant="tertiary" onClick={handleSaveDraft}>
                Save Draft
              </Button>
            </div>
          </div>
        </Card>
      </motion.div>
      )}

      {step === 1 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <h3 className="text-xl mb-6">Processing Quiz</h3>
            <ProgressBar progress={progress} className="mb-6" />
            <p className="text-xs text-[#9CA3AF] mb-4">
              Quiz generation runs several AI passes (chunking, structuring and question creation).
              Large PDFs (30–40+ pages) can take up to 1–2 minutes to finish. You can stay on this
              page while the quiz is being prepared.
            </p>
            <div className="glass-dark rounded-xl p-4 bg-[#0F172A] max-h-80 overflow-y-auto">
              <div className="space-y-2" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                {logs.map((log, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="text-sm text-[#E3EBFF]"
                  >
                    {log}
                  </motion.div>
                ))}
                {statusText && (
                  <motion.div
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="text-sm text-[#A5B4FC]"
                  >
                    Status: {statusText}
                  </motion.div>
                )}
                {errorText && (
                  <motion.div
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="text-sm text-[#FCA5A5]"
                  >
                    Error: {errorText}
                  </motion.div>
                )}
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {step === 2 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-[#22C55E]/10 flex items-center justify-center">
                <Sparkles size={24} className="text-[#22C55E]" />
              </div>
              <div>
                <h3 className="text-xl">Quiz Ready!</h3>
                <p className="text-[#9CA3AF]">
                  {statusText?.toLowerCase().includes("pending_review")
                    ? "Quiz generated and awaiting admin approval."
                    : "Your adaptive quiz has been generated successfully"}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="glass rounded-xl p-4">
                <p className="text-sm text-[#9CA3AF] mb-1">Questions</p>
                <p className="text-2xl">{formData.questionLimit}</p>
              </div>
              <div className="glass rounded-xl p-4">
                <p className="text-sm text-[#9CA3AF] mb-1">Difficulty</p>
                <p className="text-2xl">Mixed</p>
              </div>
              <div className="glass rounded-xl p-4">
                <p className="text-sm text-[#9CA3AF] mb-1">Status</p>
                <p className="text-2xl text-[#22C55E]">Ready</p>
              </div>
            </div>

            <div className="flex gap-3">
              <Button
                variant="primary"
                icon={Download}
                asChild
                disabled={!ready || (!lastTestId && !lastDownloads.pdf)}
              >
                <a href={pdfHref} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
              </Button>
              <Button
                variant="tertiary"
                icon={Eye}
                disabled={!ready || !lastTestId}
                onClick={openPreview}
              >
                Preview Questions
              </Button>
              {teacherCanAssign && (
                <Button
                  variant="secondary"
                  icon={Users}
                  disabled={!canAssignNow}
                  onClick={() => {
                    setAssignClassId(teacherClasses[0]?.id || "");
                    setAssignModalOpen(true);
                    if (lastTestId) loadAssignedClasses(lastTestId);
                  }}
                >
                  Assign to Class
                </Button>
              )}
              <Button
                variant="secondary"
                disabled={!ready || !lastTestId}
                onClick={async () => {
                  if (!lastTestId) return;
                  const confirmed = window.confirm(
                    "Delete this generated test permanently? This cannot be undone."
                  );
                  if (!confirmed) return;
                  try {
                    await api(`/api/tests/${lastTestId}`, { method: "DELETE" });
                    showToast("Test deleted", "success");
                    setStep(0);
                    setProgress(0);
                    setLogs([]);
                    setLastTestId(null);
                    setLastDownloads({});
                    setStatusText("");
                    setErrorText("");
                    setFormData({
                      file: null,
                      apiKey: "",
                      model: "llama-3.3-70b",
                      questionLimit: "30",
                      comment: "",
                      conceptsInclude: "",
                      conceptsExclude: "",
                      difficultyEasy: "30",
                      difficultyMedium: "50",
                      difficultyHard: "20",
                      bloom: {
                        understand: true,
                        apply: true,
                        analyze: false,
                        evaluate: false,
                        create: false,
                      },
                    });
                  } catch (err: any) {
                    showToast(err?.message || "Failed to delete test", "error");
                  }
                }}
              >
                Delete Test
              </Button>
            </div>

            <div className="mt-6 pt-6 border-t border-[#1E293B]/10">
              <Button
                variant="tertiary"
                onClick={() => {
                  setStep(0);
                  setProgress(0);
                  setLogs([]);
                  setLastTestId(null);
                  setLastDownloads({});
                  setFormData({
                    file: null,
                    apiKey: "",
                    model: "llama-3.3-70b",
                    questionLimit: "30",
                    comment: "",
                    conceptsInclude: "",
                    conceptsExclude: "",
                    difficultyEasy: "30",
                    difficultyMedium: "50",
                    difficultyHard: "20",
                    bloom: {
                      understand: true,
                      apply: true,
                      analyze: false,
                      evaluate: false,
                      create: false,
                    },
                  });
                }}
              >
                Create Another Quiz
              </Button>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => {
          setShowPreviewModal(false);
          setPreviewQuiz(null);
        }}
        title={formData.file?.name || "Quiz Preview"}
        description="Preview the generated questions and structure for this quiz"
        size="xl"
      >
        {previewLoading && <p className="text-sm text-[#9CA3AF]">Loading quiz...</p>}
        {!previewLoading && !previewQuiz && (
          <p className="text-sm text-[#EF4444]">No quiz data available for this test.</p>
        )}
        {!previewLoading && previewQuiz && (
          <div className="space-y-4">
            <div className="glass rounded-xl p-4 bg-[#E3EBFF]/30">
              <p className="text-sm text-[#9CA3AF] mb-1">
                {previewQuiz.course?.title || previewQuiz.title || formData.file?.name || "Preview"}
              </p>
              <p className="text-xs text-[#9CA3AF]">
                This is a read-only preview of the generated quiz structure.
              </p>
            </div>

            <div className="space-y-3 max-h-[480px] overflow-y-auto pr-2">
              {extractPreviewQuestions(previewQuiz)
                .slice(0, Math.min(100, Math.max(1, parseInt(formData.questionLimit, 10) || 30)))
                .map((q, idx) => (
                <div key={idx} className="glass rounded-xl p-4">
                  <p className="text-xs text-[#9CA3AF] mb-1">{q.context}</p>
                  <p className="text-sm font-medium mb-2">
                    {idx + 1}. {q.question}
                  </p>
                  {q.options && q.options.length > 0 && (
                    <ul className="list-disc list-inside text-xs text-[#475569] space-y-1">
                      {q.options.map((opt, i) => (
                        <li key={i}>{opt}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>

      <Modal
        isOpen={assignModalOpen}
        onClose={() => {
          setAssignModalOpen(false);
          setAssignClassId("");
          setAssignedClasses([]);
        }}
        title="Assign Test to Class"
        description="Assign this generated test to one of your classes"
        footer={
          <>
            <Button variant="tertiary" onClick={() => setAssignModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={Users}
              disabled={assigning || !canAssignNow || !assignClassId}
              onClick={async () => {
                if (!lastTestId || !assignClassId) return;
                try {
                  setAssigning(true);
                  const res = await api<any>("/api/tests/assign", {
                    method: "POST",
                    body: JSON.stringify({ test_id: lastTestId, class_id: assignClassId }),
                  });
                  showToast(res?.already_assigned ? "Already assigned (roster updated)" : "Test assigned to class", res?.already_assigned ? "info" : "success");
                  await loadAssignedClasses(lastTestId);
                  setAssignModalOpen(false);
                } catch (err: any) {
                  showToast(err?.message || "Failed to assign test", "error");
                } finally {
                  setAssigning(false);
                }
              }}
            >
              {assigning ? "Assigning..." : "Assign"}
            </Button>
          </>
        }
      >
        {teacherClasses.length === 0 ? (
          <p className="text-sm text-[#9CA3AF]">
            You are not assigned to any classes yet. Ask the admin to assign you to a class first.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="glass rounded-xl p-3">
              <p className="text-sm text-[#475569] mb-2">Already Assigned To</p>
              {assignedLoading ? (
                <p className="text-sm text-[#9CA3AF]">Loading...</p>
              ) : assignedClasses.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {assignedClasses.map((c) => (
                    <span
                      key={`${c.class_id || c.class_name}`}
                      className="px-2 py-1 rounded-full bg-[#4169E1]/10 text-[#4169E1] text-xs"
                    >
                      {c.class_name}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#9CA3AF]">Not assigned to any class yet.</p>
              )}
            </div>

            <div className="space-y-2">
              <label className="text-sm text-[#475569]">Select class</label>
            <select
              className="w-full glass rounded-xl px-3 py-2 outline-none"
              value={assignClassId}
              onChange={(e) => setAssignClassId(e.target.value)}
            >
              {teacherClasses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
