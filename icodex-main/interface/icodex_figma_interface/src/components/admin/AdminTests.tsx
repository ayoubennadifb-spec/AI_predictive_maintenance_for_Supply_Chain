import { useEffect, useState } from "react";
import { CheckCircle, FileText, Download } from "lucide-react";
import { Hero } from "../Hero";
import { Table } from "../Table";
import { Button } from "../Button";
import { Modal } from "../Modal";
import { Select, Input } from "../Input";
import { StatusChip, Chip } from "../Chip";
import { Tabs } from "../Tabs";
import { useToast } from "../Toast";
import { api } from "../../utils/api";

export function AdminTests() {
  const [activeTab, setActiveTab] = useState("pending");
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [selectedTest, setSelectedTest] = useState<any>(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewQuiz, setPreviewQuiz] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showRerunModal, setShowRerunModal] = useState(false);
  const [rerunTarget, setRerunTarget] = useState<any>(null);
  const [rerunApiKey, setRerunApiKey] = useState("");
  const [rerunModel, setRerunModel] = useState("llama-3.1-8b");
  const { showToast } = useToast();

  const [pendingTests, setPendingTests] = useState<any[]>([]);
  const [approvedTests, setApprovedTests] = useState<any[]>([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [classOptions, setClassOptions] = useState<{ value: string; label: string }[]>([]);
  const [loadingPending, setLoadingPending] = useState(true);
  const [loadingApproved, setLoadingApproved] = useState(true);
  const [rerunLoading, setRerunLoading] = useState<string | null>(null);

  const modelOptions = [
    { value: "llama-3.3-70b", label: "Llama 3.3 70B (Recommended)" },
    { value: "llama-3.1-8b", label: "Llama 3.1 8B (Fast)" },
    { value: "mixtral-8x7b", label: "Mixtral 8x7B (Balanced)" },
  ];

  const fetchTests = async () => {
    try {
      const data = await api<{ tests: any[] }>('/api/tests');
      const pendingRaw = (data.tests || []).filter((t) => (t.kind === 'class_test'));
      const pending = pendingRaw.filter(
        (t) => (t.status || '').startsWith('pending') || (t.status || '').startsWith('failed')
      );
      const approved = (data.tests || []).filter((t) => (t.kind === 'class_test') && (t.status === 'ready' || t.status === 'approved'));
      const normalize = (test: any) => ({
        id: test.id,
        title: test.title,
        owner: test.ownerName || test.owner || test.ownerId || 'Unknown',
        questionLimit: test.questionLimit || test.limit,
        comment: test.comment,
        status: test.status,
        assignedClass: test.assignedClass,
        quizPdfPath: test.quizPdfPath || test.paths?.quiz_pdf,
        hasQuiz: !!(test.quizPdfPath || test.paths?.quiz_pdf),
        error: test.error || (test.status && test.status.startsWith('failed') ? test.status : ""),
        quality: test.quality,
        review: test.review,
        pipeline: test.pipeline,
      });
      setPendingTests(pending.map(normalize));
      setApprovedTests(approved.map(normalize));
    } catch (err: any) {
      showToast(err?.message || "Failed to load tests", "error");
    } finally {
      setLoadingPending(false);
      setLoadingApproved(false);
    }
  };

  const fetchClasses = async () => {
    try {
      const data = await api<{ classes: any[] }>('/api/classes');
      const opts = (data.classes || []).map((c: any) => ({ value: c.id, label: c.name }));
      setClassOptions([{ value: "", label: "Select a class" }, ...opts]);
    } catch (err: any) {
      showToast(err?.message || "Failed to load classes", "error");
    }
  };

  useEffect(() => {
    fetchTests();
    fetchClasses();
  }, []);

  const openPreview = async (test: any) => {
    try {
      setPreviewLoading(true);
      setSelectedTest(test);
      const quiz = await api<any>(`/api/tests/${test.id}/quiz`);
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

  const renderDistribution = (dist: Record<string, number> | undefined, color: string) => {
    const entries = Object.entries(dist || {}).filter(([, count]) => count);
    if (!entries.length) return <p className="text-xs text-[#9CA3AF]">No data</p>;
    const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;
    return (
      <div className="space-y-2">
        {entries.map(([label, count]) => (
          <div key={label} className="space-y-1">
            <div className="flex justify-between text-xs text-[#475569]">
              <span>{label.replace(/_/g, " ")}</span>
              <span>{count}</span>
            </div>
            <div className="h-2 bg-[#E5E7EB] rounded-full overflow-hidden">
              <div className="h-full" style={{ width: `${Math.round((count / total) * 100)}%`, backgroundColor: color }} />
            </div>
          </div>
        ))}
      </div>
    );
  };

  const handleRerunConfirm = async () => {
    if (!rerunTarget) return;
    try {
      setRerunLoading(rerunTarget.id);
      await api(`/api/tests/${rerunTarget.id}/rerun`, {
        method: "POST",
        body: JSON.stringify({
          apiKey: rerunApiKey,
          model: rerunModel,
        }),
      });
      showToast("Re-run started", "info");
      setShowRerunModal(false);
      setRerunTarget(null);
      setRerunApiKey("");
      setRerunModel("llama-3.1-8b");
      fetchTests();
    } catch (err: any) {
      showToast(err?.message || "Failed to re-run", "error");
    } finally {
      setRerunLoading(null);
    }
  };

  const handleApprove = async () => {
    if (!selectedClass) {
      showToast("Please select a class", "error");
      return;
    }
    if (!selectedTest) return;
    try {
      await api('/api/tests/approve', {
        method: 'POST',
        body: JSON.stringify({ test_id: selectedTest.id, class_id: selectedClass }),
      });
      showToast("Test approved and assigned", "success");
      setShowApproveModal(false);
      setSelectedTest(null);
      setSelectedClass("");
      fetchTests();
    } catch (err: any) {
      showToast(err?.message || "Failed to approve test", "error");
    }
  };

  const pendingColumns = [
    { key: "title", label: "Test Title" },
    { key: "owner", label: "Created By" },
    { key: "questionLimit", label: "Questions" },
    { key: "comment", label: "Comment" },
    {
      key: "quality",
      label: "Quality",
      render: (test: any) => {
        const score = test.quality?.quality_score;
        if (score == null) return <span className="text-xs text-[#9CA3AF]">—</span>;
        const variant = score >= 75 ? "success" : score >= 55 ? "warning" : "error";
        return (
          <Chip variant={variant as any} size="sm">
            {score}%
          </Chip>
        );
      },
    },
    {
      key: "status",
      label: "Status",
      render: (test: any) => (
        <StatusChip status={test.status && test.status.startsWith("failed") ? "failed" : "pending"} />
      ),
    },
    {
      key: "review",
      label: "AI Review",
      render: (test: any) => {
        const notes = test.review?.notes || [];
        const severity = test.review?.severity || "info";
        const variant =
          severity === "critical" ? "error" : severity === "warning" ? "warning" : "info";
        return notes.length ? (
          <Chip variant={variant as any} size="sm">
            {notes[0]}
          </Chip>
        ) : (
          <span className="text-xs text-[#9CA3AF]">No notes</span>
        );
      },
    },
    {
      key: "actions",
      label: "Actions",
      render: (test: any) => (
        <div className="flex gap-2">
          {!(test.error && !test.hasQuiz) && (
            <Button
              variant="primary"
              size="sm"
              icon={CheckCircle}
              disabled={!!test.error || !test.hasQuiz}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedTest(test);
                setShowApproveModal(true);
              }}
            >
              Approve
            </Button>
          )}
          {test.error && (
            <Button
              variant="secondary"
              size="sm"
              disabled={rerunLoading === test.id}
              onClick={(e) => {
                e.stopPropagation();
                setRerunTarget(test);
                setShowRerunModal(true);
              }}
            >
              {rerunLoading === test.id ? "Re-running..." : "Re-run"}
            </Button>
          )}
          <Button
            variant="tertiary"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              openPreview(test);
            }}
          >
            {previewLoading && selectedTest?.id === test.id ? "Loading..." : "Preview"}
          </Button>
          <Button
            variant="tertiary"
            size="sm"
            onClick={async () => {
              if (!window.confirm("Delete this test permanently? This will also remove related assignments.")) return;
              try {
                await api(`/api/tests/${test.id}`, { method: "DELETE" });
                showToast("Test deleted", "success");
                fetchTests();
              } catch (err: any) {
                showToast(err?.message || "Failed to delete test", "error");
              }
            }}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  const approvedColumns = [
    { key: "title", label: "Test Title" },
    { key: "owner", label: "Created By" },
    { key: "questionLimit", label: "Questions" },
    { key: "assignedClass", label: "Assigned To" },
    {
      key: "quality",
      label: "Quality",
      render: (test: any) => {
        const score = test.quality?.quality_score;
        if (score == null) return <span className="text-xs text-[#9CA3AF]">—</span>;
        const variant = score >= 75 ? "success" : score >= 55 ? "warning" : "error";
        return (
          <Chip variant={variant as any} size="sm">
            {score}%
          </Chip>
        );
      },
    },
    {
      key: "status",
      label: "Status",
      render: (test: any) => <StatusChip status="approved" />,
    },
    {
      key: "actions",
      label: "Actions",
      render: (test: any) => (
        <div className="flex flex-col gap-1">
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" icon={Download} asChild>
              <a href={`/api/tests/${test.id}/quiz?format=pdf`} target="_blank" rel="noreferrer">
                PDF
              </a>
            </Button>
            <Button
              variant="tertiary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                openPreview(test);
              }}
            >
              Preview
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              variant="primary"
              size="sm"
              icon={CheckCircle}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedTest(test);
                setShowApproveModal(true);
              }}
            >
              Assign to Class
            </Button>
            <Button
              variant="tertiary"
              size="sm"
              onClick={async (e) => {
                e.stopPropagation();
                if (!window.confirm("Delete this test permanently? This will also remove related assignments.")) {
                  return;
                }
                try {
                  await api(`/api/tests/${test.id}`, { method: "DELETE" });
                  showToast("Test deleted", "success");
                  fetchTests();
                } catch (err: any) {
                  showToast(err?.message || "Failed to delete test", "error");
                }
              }}
            >
              Delete
            </Button>
          </div>
          {test.error && (
            <div className="text-xs text-[#EF4444]">Error: {test.error}</div>
          )}
        </div>
      ),
    },
  ];

  const tabs = [
    { id: "pending", label: "Pending", count: pendingTests.length },
    { id: "approved", label: "Approved", count: approvedTests.length },
  ];

  return (
    <div>
      <Hero
        title="Test Management"
        description="Review and approve teacher-submitted tests, assign to classes"
      />

      <div className="mb-6">
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
      </div>

      {activeTab === "pending" ? (
        <Table data={pendingTests} columns={pendingColumns} loading={loadingPending} />
      ) : (
        <Table data={approvedTests} columns={approvedColumns} loading={loadingApproved} />
      )}

      {/* Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => {
          setShowPreviewModal(false);
          setPreviewQuiz(null);
          setSelectedTest(null);
        }}
        title={selectedTest?.title || "Quiz Preview"}
        description="Preview the generated questions and structure for this test"
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
                {previewQuiz.course?.title || previewQuiz.title || selectedTest?.title || "Preview"}
              </p>
              {previewQuiz.course?.description && (
                <p className="text-sm text-[#475569]">{previewQuiz.course.description}</p>
              )}
            </div>
            {selectedTest?.quality && (
              <div className="glass rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-sm text-[#9CA3AF]">Test Quality</p>
                    <p className="text-lg font-semibold">{selectedTest.quality.quality_score}% score</p>
                  </div>
                  {selectedTest.review && (
                    <Chip variant="info" size="sm">
                      {selectedTest.review.summary || "Auto review"}
                    </Chip>
                  )}
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-[#9CA3AF] mb-2">Difficulty Distribution</p>
                    {renderDistribution(selectedTest.quality.difficulty_distribution, "#4169E1")}
                  </div>
                  <div>
                    <p className="text-xs text-[#9CA3AF] mb-2">Bloom Coverage</p>
                    {renderDistribution(selectedTest.quality.bloom_distribution, "#7C3AED")}
                  </div>
                </div>
                <div className="mt-4">
                  <p className="text-xs text-[#9CA3AF] mb-2">Concept Coverage</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(selectedTest.quality.concept_distribution || {})
                      .slice(0, 8)
                      .map(([concept, count]) => (
                        <Chip key={concept} variant="secondary" size="sm">
                          {concept} · {count}
                        </Chip>
                      ))}
                    {Object.keys(selectedTest.quality.concept_distribution || {}).length === 0 && (
                      <span className="text-xs text-[#9CA3AF]">No concepts detected</span>
                    )}
                  </div>
                </div>
                {selectedTest.review?.notes?.length > 0 && (
                  <div className="mt-4">
                    <p className="text-xs text-[#9CA3AF] mb-2">AI Review Notes</p>
                    <ul className="text-xs text-[#475569] space-y-1">
                      {selectedTest.review.notes.map((note: string, idx: number) => (
                        <li key={idx}>• {note}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {(() => {
              const questions = extractPreviewQuestions(previewQuiz);
              if (!questions.length) {
                return <p className="text-sm text-[#9CA3AF]">No questions found in quiz JSON.</p>;
              }
              return (
                <div className="space-y-3">
                  <p className="text-sm text-[#9CA3AF]">
                    Showing {questions.length} questions extracted from the quiz.
                  </p>
                  {questions.map((q, idx) => (
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
                  ))}
                </div>
              );
            })()}
          </div>
        )}
      </Modal>

      {/* Approve Modal */}
      <Modal
        isOpen={showApproveModal}
        onClose={() => {
          setShowApproveModal(false);
          setSelectedTest(null);
          setSelectedClass("");
        }}
        title="Approve & Assign Test"
        description={`Approve "${selectedTest?.title}" and assign it to a class`}
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={() => {
                setShowApproveModal(false);
                setSelectedTest(null);
                setSelectedClass("");
              }}
            >
              Cancel
            </Button>
            <Button variant="primary" icon={CheckCircle} onClick={handleApprove}>
              Approve & Assign
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="glass rounded-xl p-4 bg-[#E3EBFF]/30">
            <p className="text-sm text-[#9CA3AF] mb-1">Test Details</p>
            <p className="mb-1">{selectedTest?.title}</p>
            <p className="text-sm text-[#9CA3AF]">
              {selectedTest?.questionLimit} questions · by {selectedTest?.owner}
            </p>
            {selectedTest?.comment && (
              <p className="text-sm text-[#475569] mt-2 italic">"{selectedTest.comment}"</p>
            )}
          </div>
        <Select
          label="Assign to Class *"
          options={classOptions}
          value={selectedClass}
          onChange={(e) => setSelectedClass(e.target.value)}
          helperText="Select which class should have access to this test"
        />
      </div>
      </Modal>

      {/* Re-run Modal */}
      <Modal
        isOpen={showRerunModal}
        onClose={() => {
          setShowRerunModal(false);
          setRerunTarget(null);
          setRerunApiKey("");
          setRerunModel("llama-3.1-8b");
        }}
        title="Re-run Quiz Generation"
        description={
          rerunTarget
            ? `Re-run the quiz generation pipeline for "${rerunTarget.title}". Optionally provide a Cerebras API key (otherwise the server's CEREBRAS_API_KEY will be used).`
            : "Re-run the quiz generation pipeline."
        }
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={() => {
                setShowRerunModal(false);
                setRerunTarget(null);
                setRerunApiKey("");
                setRerunModel("llama-3.1-8b");
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={CheckCircle}
              onClick={handleRerunConfirm}
              disabled={!!rerunLoading}
            >
              {rerunLoading ? "Re-running..." : "Start Re-run"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Cerebras API Key (optional)"
            type="password"
            placeholder="csk-..."
            value={rerunApiKey}
            onChange={(e) => setRerunApiKey(e.target.value)}
            helperText="Optional if the server has CEREBRAS_API_KEY set. Used only for this re-run; not stored in app state."
          />
          <Select
            label="AI Model"
            value={rerunModel}
            onChange={(e) => setRerunModel(e.target.value)}
            options={modelOptions}
            helperText="Choose the model for this retry"
          />
        </div>
      </Modal>
    </div>
  );
}
