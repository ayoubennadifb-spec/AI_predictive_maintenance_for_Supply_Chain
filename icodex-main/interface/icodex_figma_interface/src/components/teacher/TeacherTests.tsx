import { useEffect, useState } from "react";
import { Download, Eye, FileText, Users, BarChart3 } from "lucide-react";
import { Hero } from "../Hero";
import { Table } from "../Table";
import { Button } from "../Button";
import { StatusChip } from "../Chip";
import { PillFilter } from "../Tabs";
import { api } from "../../utils/api";
import { useToast } from "../Toast";
import { Modal } from "../Modal";

export function TeacherTests() {
  const [filterStatus, setFilterStatus] = useState("all");
  const [tests, setTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewQuiz, setPreviewQuiz] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [selectedTest, setSelectedTest] = useState<any | null>(null);
  const [teacherCanAssign, setTeacherCanAssign] = useState(false);
  const [teacherClasses, setTeacherClasses] = useState<{ id: string; name: string }[]>([]);
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [assignTest, setAssignTest] = useState<any | null>(null);
  const [assignClassId, setAssignClassId] = useState("");
  const [assignDue, setAssignDue] = useState("");
  const [assignMode, setAssignMode] = useState<"adaptive" | "fixed">("adaptive");
  const [assignTimeLimit, setAssignTimeLimit] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [assignedClasses, setAssignedClasses] = useState<{ class_id: string | null; class_name: string }[]>([]);
  const [assignedLoading, setAssignedLoading] = useState(false);
  const { showToast } = useToast();

  const fetchTests = async () => {
    try {
      const data = await api<{ tests: any[] }>('/api/tests/my-tests');
      const normalized = (data.tests || []).map((t) => {
        const rawStatus = (t.status || "").toLowerCase();
        const status = rawStatus.startsWith("failed")
          ? "failed"
          : rawStatus.startsWith("pending")
          ? "pending_review"
          : rawStatus;
        const quality = t.quality || {};
        const conceptDist = quality.concept_distribution || {};
        const difficulty = quality.difficulty_distribution || {};
        return {
          id: t.id,
          title: t.title,
          status,
          questionLimit: t.questionLimit || t.limit,
          createdAt: t.createdAt || t.created_at || new Date().toISOString(),
          quizPdfPath: t.quizPdfPath || t.paths?.quiz_pdf,
          quizJsonPath: t.quizJsonPath || t.paths?.quiz_json,
          error: t.error || (rawStatus.startsWith("failed") ? t.status : ""),
          rawStatus: t.status,
          qualityScore: quality.quality_score,
          conceptDist,
          difficulty,
        };
      });
      setTests(normalized);
    } catch (err: any) {
      showToast(err?.message || "Failed to load tests", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTests();
  }, []);

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

  useEffect(() => {
    const loadConfigAndClasses = async () => {
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
    };
    loadConfigAndClasses();
  }, []);

  const filteredTests = tests.filter(
    (test) => filterStatus === "all" || test.status === filterStatus
  );

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

  const statusFilters = [
    { id: "all", label: "All Tests" },
    { id: "ready", label: "Ready", color: "#22C55E" },
    { id: "processing", label: "Processing", color: "#F97316" },
    { id: "pending_review", label: "Pending Review", color: "#F97316" },
    { id: "failed", label: "Failed", color: "#EF4444" },
  ];

  const columns = [
    { key: "title", label: "Test Title" },
    {
      key: "status",
      label: "Status",
      render: (test: any) => <StatusChip status={test.status} />,
    },
    {
      key: "coverage",
      label: "Concepts",
      render: (test: any) => {
        const entries = Object.entries(test.conceptDist || {})
          .sort((a: any, b: any) => b[1] - a[1])
          .slice(0, 3);
        if (!entries.length) return <span className="text-xs text-[#9CA3AF]">--</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {entries.map(([c]) => (
              <span key={c} className="px-2 py-1 rounded-full bg-[#4169E1]/10 text-[#4169E1] text-xs">
                {c}
              </span>
            ))}
          </div>
        );
      },
    },
    {
      key: "difficulty",
      label: "Difficulty",
      render: (test: any) => {
        const d = test.difficulty || {};
        const total =
          (d.easy || 0) + (d.medium || 0) + (d.hard || 0) + (d.very_hard || 0) + (d.unknown || 0);
        if (!total) return <span className="text-xs text-[#9CA3AF]">--</span>;
        const pct = (k: string) => Math.round(((d[k] || 0) / total) * 100);
        return (
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-[10px] text-[#6B7280]">
              <span>E</span><span>{pct("easy")}%</span>
              <span>M</span><span>{pct("medium")}%</span>
              <span>H</span><span>{pct("hard") + pct("very_hard")}%</span>
            </div>
            <div className="h-1.5 w-full bg-[#E5E7EB] rounded-full overflow-hidden">
              <div className="h-full bg-[#22C55E]" style={{ width: `${pct("easy")}%` }} />
              <div className="h-full bg-[#7C3AED]" style={{ width: `${pct("medium")}%` }} />
              <div className="h-full bg-[#F97316]" style={{ width: `${pct("hard") + pct("very_hard")}%` }} />
            </div>
          </div>
        );
      },
    },
    {
      key: "questionLimit",
      label: "Questions",
      render: (test: any) => <span>{test.questionLimit}</span>,
    },
    { key: "createdAt", label: "Created At" },
    {
      key: "qualityScore",
      label: "Quality",
      render: (test: any) =>
        test.qualityScore != null ? (
          <div className="flex items-center gap-1 text-sm">
            <BarChart3 size={14} className="text-[#4169E1]" /> {test.qualityScore}
          </div>
        ) : (
          <span className="text-xs text-[#9CA3AF]">--</span>
        ),
    },
    {
      key: "error",
      label: "Error",
      render: (test: any) =>
        test.status === "failed" ? (
          <span className="text-[#EF4444] text-xs">{test.error || "Failed"}</span>
        ) : (
          <span className="text-xs text-[#9CA3AF]">—</span>
        ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (test: any) => (
        <div className="flex flex-wrap gap-2">
          {(test.status === "ready" || test.status === "pending_review") && (
            <>
              <Button variant="primary" size="sm" icon={Download} asChild>
                <a href={`/api/tests/${test.id}/quiz?format=pdf`} target="_blank" rel="noreferrer">
                  Download
                </a>
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={Eye}
                onClick={() => openPreview(test)}
              >
                Preview
              </Button>
              {test.status === "pending_review" && (
                <Button variant="tertiary" size="sm" onClick={() => showToast("Waiting admin approval", "info")}>
                  Awaiting Approval
                </Button>
              )}
              {teacherCanAssign && test.status === "ready" && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Users}
                  disabled={teacherClasses.length === 0}
                  onClick={() => {
                    setAssignTest(test);
                    setAssignClassId(teacherClasses[0]?.id || "");
                    setAssignModalOpen(true);
                    loadAssignedClasses(test.id);
                  }}
                >
                  Assign
                </Button>
              )}
            </>
          )}
          {test.status === "processing" && (
            <Button variant="tertiary" size="sm" onClick={() => showToast("Processing... check back soon", "info")}>
              View Logs
            </Button>
          )}
          {test.status === "failed" && (
            <Button variant="secondary" size="sm" onClick={() => showToast("Retry upload in Quiz Studio", "info")}>
              Retry
            </Button>
          )}
          <Button
            variant="tertiary"
            size="sm"
            onClick={async () => {
              if (!window.confirm("Delete this test permanently? This cannot be undone.")) return;
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

  return (
    <div>
      <Hero
        title="My Tests"
        description="View and manage all your created tests and their processing status"
      />

      <div className="mb-6">
        <PillFilter
          filters={statusFilters}
          activeFilter={filterStatus}
          onChange={setFilterStatus}
        />
      </div>

      <Table data={filteredTests} columns={columns} loading={loading} />

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
              <p className="text-xs text-[#9CA3AF]">
                This is a read-only preview of the generated quiz structure.
              </p>
            </div>

            <div className="space-y-3 max-h-[480px] overflow-y-auto pr-2">
              {extractPreviewQuestions(previewQuiz).map((q, idx) => (
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
          setAssignTest(null);
          setAssignClassId("");
          setAssignedClasses([]);
        }}
        title={`Assign "${assignTest?.title || ""}"`}
        description="Assign this test to one of your classes"
        footer={
          <>
            <Button variant="tertiary" onClick={() => setAssignModalOpen(false)}>
              Cancel
            </Button>
              <Button
                variant="primary"
                icon={FileText}
                disabled={assigning || !assignTest || !assignClassId}
                onClick={async () => {
                  if (!assignTest || !assignClassId) return;
                  try {
                    setAssigning(true);
                    const res = await api<any>("/api/tests/assign", {
                      method: "POST",
                      body: JSON.stringify({
                        test_id: assignTest.id,
                        class_id: assignClassId,
                        due_date: assignDue || undefined,
                        mode: assignMode,
                        time_limit_minutes: assignTimeLimit ? Number(assignTimeLimit) : undefined,
                      }),
                    });
                    showToast(res?.already_assigned ? "Already assigned (roster updated)" : "Test assigned to class", res?.already_assigned ? "info" : "success");
                    await loadAssignedClasses(assignTest.id);
                    setAssignModalOpen(false);
                    setAssignTest(null);
                    setAssignClassId("");
                    setAssignDue("");
                    setAssignMode("adaptive");
                    setAssignTimeLimit("");
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-[#475569]">Due date (optional)</label>
                <input
                  type="date"
                  className="w-full glass rounded-xl px-3 py-2 outline-none"
                  value={assignDue}
                  onChange={(e) => setAssignDue(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm text-[#475569]">Time limit (mins, optional)</label>
                <input
                  type="number"
                  min={5}
                  className="w-full glass rounded-xl px-3 py-2 outline-none"
                  value={assignTimeLimit}
                  onChange={(e) => setAssignTimeLimit(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm text-[#475569]">Mode</label>
              <div className="flex gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="assign-mode"
                    checked={assignMode === "adaptive"}
                    onChange={() => setAssignMode("adaptive")}
                  />
                  Adaptive
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="assign-mode"
                    checked={assignMode === "fixed"}
                    onChange={() => setAssignMode("fixed")}
                  />
                  Fixed
                </label>
              </div>
              <p className="text-xs text-[#9CA3AF]">Adaptive reorders/adjusts difficulty; Fixed keeps original order.</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
