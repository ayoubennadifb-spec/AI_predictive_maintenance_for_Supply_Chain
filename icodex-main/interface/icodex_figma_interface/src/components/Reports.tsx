import { useEffect, useMemo, useState } from "react";
import { Download, Eye, BarChart3, Trash2, Sparkles } from "lucide-react";
import { Hero } from "./Hero";
import { Card } from "./Card";
import { Chip } from "./Chip";
import { Button } from "./Button";
import { PillFilter } from "./Tabs";
import { motion } from "motion/react";
import { api } from "../utils/api";
import { useToast } from "./Toast";
import { Modal } from "./Modal";

export function Reports() {
  const [filterType, setFilterType] = useState("all");
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();
  const [emptyState, setEmptyState] = useState(false);
  const [assignmentResults, setAssignmentResults] = useState<any[]>([]);
  const [isTeacherOrAdmin, setIsTeacherOrAdmin] = useState(false);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [studentOverview, setStudentOverview] = useState<any>(null);
  const [masteryModalOpen, setMasteryModalOpen] = useState(false);
  const [masteryLoading, setMasteryLoading] = useState(false);
  const [masteryData, setMasteryData] = useState<any>(null);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [insights, setInsights] = useState<any>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailReport, setDetailReport] = useState<any>(null);
  const [detailInsights, setDetailInsights] = useState<any>(null);
  const [detailMastery, setDetailMastery] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const canDeleteReport = (report: any) => {
    const role = String(currentUser?.role || "").toLowerCase();
    const baseId = report?.testId || report?.id;
    if (!baseId) return false;

    if (role === "admin") return true;

    const ownerId = report?.ownerId;
    const userId = currentUser?.id;
    if (role === "teacher") return Boolean(ownerId && userId && ownerId === userId);

    if (role === "student") {
      const kind = String(report?.kind || report?.type || "").toLowerCase();
      return Boolean(kind === "practice" && ownerId && userId && ownerId === userId);
    }

    return false;
  };

  const canDeleteTestId = (testId?: string) => {
    const id = String(testId || "");
    if (!id) return false;
    const match = (reports || []).find((r) => (r?.testId || r?.id) === id);
    return canDeleteReport(match || { id, testId: id });
  };

  const deleteTest = async (testId: string) => {
    if (!testId) return;
    if (!window.confirm("Delete this test permanently? This cannot be undone.")) return;
    try {
      setDeleting(testId);
      await api(`/api/tests/${testId}`, { method: "DELETE" });
      showToast("Test deleted", "success");
      setReports((prev) => {
        const next = (prev || []).filter((r) => (r.testId || r.id) !== testId);
        setEmptyState(next.length === 0);
        return next;
      });
      setAssignmentResults((prev) => (prev || []).filter((r) => r.testId !== testId));
    } catch (err: any) {
      showToast(err?.message || "Failed to delete test", "error");
    } finally {
      setDeleting(null);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const me = await api<{ user: any }>('/api/auth/me').catch(() => null);
        if (me?.user) setCurrentUser(me.user);
        const role = String(me?.user?.role || "").toLowerCase();
        if (role === "student") {
          const overviewRes = await api<any>("/api/student/overview").catch(() => null);
          setStudentOverview(overviewRes);
        }
        const testsRes = await api<{ tests: any[] }>('/api/tests').catch(() => ({ tests: [] }));
        const myTests = await api<{ tests: any[] }>('/api/tests/my-tests').catch(() => ({ tests: [] }));
        const assignments = await api<{ assignments: any[] }>('/api/assignments/my-assignments').catch(() => ({ assignments: [] }));
        const practiceHistory = role === "student"
          ? await api<{ sessions: any[] }>("/api/student/practice/history").catch(() => ({ sessions: [] }))
          : { sessions: [] };
        const assignmentAgg = await api<{ assignments: any[] }>('/api/assignments/results')
          .then((res) => {
            setIsTeacherOrAdmin(true);
            return res;
          })
          .catch(() => {
            setIsTeacherOrAdmin(false);
            return { assignments: [] };
          });
        setInsightsLoading(true);
        const insightsRes = await api<any>("/api/reports/insights").catch(() => null);
        setInsights(insightsRes);
        setInsightsLoading(false);

        // Build average score per test from aggregated assignment results (teachers/admin only)
        const avgByTestId: Record<string, { score: number; questions: number }> = {};
        const accumByTestId: Record<string, { sum: number; count: number; questions: number }> = {};

        (assignmentAgg.assignments || []).forEach((a: any) => {
          const testId = a.test?.id;
          if (!testId) return;
          const results = a.results || [];
          results.forEach((r: any) => {
            if (typeof r.percent !== "number") return;
            const key = testId;
            const qCount =
              r.limit ??
              r.totalQuestions ??
              a.totalQuestions ??
              a.test?.questionLimit ??
              0;
            if (!accumByTestId[key]) {
              accumByTestId[key] = { sum: 0, count: 0, questions: qCount };
            }
            accumByTestId[key].sum += r.percent;
            accumByTestId[key].count += 1;
            if (!accumByTestId[key].questions && qCount) {
              accumByTestId[key].questions = qCount;
            }
          });
        });

        Object.entries(accumByTestId).forEach(([testId, agg]) => {
          if (agg.count > 0) {
            avgByTestId[testId] = {
              score: Math.round(agg.sum / agg.count),
              questions: agg.questions,
            };
          }
        });

        let mappedReports: any[] = [];

        if (role === "student") {
          const lookupTests = (myTests?.tests as any[]) || [];
          const testById = new Map(lookupTests.map((t: any) => [t.id, t]));
          mappedReports = (practiceHistory.sessions || []).map((session: any) => {
            const test = testById.get(session.test_id) || {};
            return {
              id: session.test_id,
              title: session.title || test.title || "Practice Quiz",
              type: "practice",
              kind: "practice",
              ownerId: test.owner_id ?? test.ownerId ?? test.owner?.id,
              date: session.completed_at || test.createdAt || test.created_at || "",
              score: session.score ?? test.score ?? 0,
              questions: session.question_count || test.questionLimit || test.limit || 0,
              pdf: test.quizPdfPath || test.paths?.quiz_pdf,
              json: test.quizJsonPath || test.paths?.quiz_json,
              timeSpent: session.time_spent ?? 0,
              strengths: session.strengths || [],
              weaknesses: session.weaknesses || [],
              testId: session.test_id,
            };
          });
        } else {
          const baseTests = [
            ...((testsRes?.tests as any[]) || []),
            ...((myTests?.tests as any[]) || []),
          ];

          const combined = baseTests
            .filter(Boolean)
            // unique by id
            .filter((t, idx, arr) => t && arr.findIndex(tt => tt.id === t.id) === idx)
            // only ready tests with a quiz pdf on disk
            .filter((t) => t?.status === "ready" && (t.quizPdfPath || t.paths?.quiz_pdf));

          mappedReports = combined.map((t) => {
            const avg = avgByTestId[t.id];
            const kind = t.kind || "test";
            const type = kind === "practice" ? "practice" : "test";
            return {
              id: t.id,
              title: t.title || "Quiz",
              type,
              kind,
              ownerId: t.owner_id ?? t.ownerId ?? t.owner?.id,
              date: t.createdAt || t.created_at || "",
              score: avg ? avg.score : t.score ?? 0,
              questions:
                (avg && typeof avg.questions === "number" && avg.questions > 0
                  ? avg.questions
                  : t.questionLimit || t.limit || 0),
              pdf: t.quizPdfPath || t.paths?.quiz_pdf,
              json: t.quizJsonPath || t.paths?.quiz_json,
              timeSpent: t.timeSpent || 0,
              strengths: t.strengths || [],
              weaknesses: t.weaknesses || [],
              testId: t.id,
            };
          });
        }

        // Add assignment completion reports if available
        (assignments.assignments || []).forEach((a: any) => {
          if (a.status === "completed") {
            mappedReports.push({
              id: a.id,
              title: a.test?.title || "Assigned Test",
              type: "test",
              kind: a.test?.kind || "test",
              ownerId: a.test?.owner_id ?? a.test?.ownerId ?? a.test?.owner?.id,
              date: a.completedAt || a.createdAt || "",
              score: a.finalScore ?? 0,
              questions: a.totalQuestions || a.test?.questionLimit || 0,
              pdf: a.test?.quizPdfPath || a.test?.paths?.quiz_pdf,
              timeSpent: a.timeSpent || 0,
              strengths: a.strengths || [],
              weaknesses: a.weaknesses || [],
              testId: a.test?.id,
            });
          }
        });

        const final = Array.isArray(mappedReports) ? mappedReports : [];
        setReports(final);
        setEmptyState(final.length === 0);

        const studentRows =
          (assignmentAgg.assignments || []).flatMap((a: any) =>
            (a.results || []).map((r: any) => ({
              assignmentId: a.assignment_id,
              testTitle: a.test?.title || "Test",
              testId: a.test?.id,
              studentName: r.student_name,
              studentId: r.student_id,
              percent: r.percent,
              strengths: r.strengths || [],
              weaknesses: r.weaknesses || [],
            })),
          ) || [];
        setAssignmentResults(studentRows);
      } catch (err: any) {
        showToast(err?.message || "Failed to load reports", "error");
        setReports([]);
        setEmptyState(true);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filteredReports = Array.isArray(reports)
    ? reports.filter((report) => filterType === "all" || report.type === filterType)
    : [];

  const filters = [
    { id: "all", label: "All Reports" },
    { id: "test", label: "Tests" },
    { id: "practice", label: "Practice" },
  ];

  const isStudent = String(currentUser?.role || "").toLowerCase() === "student";

  const studentOptionsByTest = useMemo(() => {
    const grouped: Record<string, any[]> = {};
    assignmentResults.forEach((r) => {
      if (!r?.testId) return;
      if (!grouped[r.testId]) grouped[r.testId] = [];
      grouped[r.testId].push(r);
    });
    return grouped;
  }, [assignmentResults]);

  const fetchMastery = async (testId: string, studentId: string) => {
    setMasteryLoading(true);
    setMasteryData(null);
    try {
      const res = await api(`/api/tests/${testId}/mastery-report?student_id=${studentId}&format=json`);
      setMasteryData(res);
    } catch (err: any) {
      showToast(err?.message || "Failed to load mastery report", "error");
    } finally {
      setMasteryLoading(false);
    }
  };

  const openMasteryModal = (testId?: string, studentId?: string) => {
    const baseId = testId || "";
    const options = studentOptionsByTest[baseId] || [];
    const chosenStudent = studentId || options[0]?.studentId;
    if (!baseId || !chosenStudent) {
      showToast("No student attempts available yet for this test", "error");
      return;
    }
    setSelectedTestId(baseId);
    setSelectedStudentId(chosenStudent);
    setMasteryModalOpen(true);
    fetchMastery(baseId, chosenStudent);
  };

  const onStudentChange = (studentId: string) => {
    if (!selectedTestId) return;
    setSelectedStudentId(studentId);
    fetchMastery(selectedTestId, studentId);
  };

  const openStudentDetail = async (report: any) => {
    if (!report?.testId && !report?.id) return;
    const testId = report.testId || report.id;
    setDetailReport(report);
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailInsights(null);
    setDetailMastery(null);
    try {
      const [insightsRes, masteryRes] = await Promise.all([
        api<any>(`/api/reports/insights?test_id=${testId}`).catch(() => null),
        currentUser?.id
          ? api<any>(`/api/tests/${testId}/mastery-report?student_id=${currentUser.id}&format=json`).catch(() => null)
          : Promise.resolve(null),
      ]);
      setDetailInsights(insightsRes);
      setDetailMastery(masteryRes);
    } catch (err: any) {
      showToast(err?.message || "Failed to load report details", "error");
    } finally {
      setDetailLoading(false);
    }
  };

  const currentStudentOptions = selectedTestId ? studentOptionsByTest[selectedTestId] || [] : [];
  const pdfLink =
    selectedTestId && selectedStudentId
      ? `/api/tests/${selectedTestId}/mastery-report?student_id=${selectedStudentId}&format=pdf`
      : undefined;

  return (
    <div>
      <Hero
        title="Performance Reports"
        description="View detailed analytics of your test and practice performance"
      />

      {isStudent && (
        <div className="grid gap-6 md:grid-cols-2 mb-8">
          <Card>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-semibold">Mastery Summary</h3>
              <Chip variant="info" size="sm">AI Insight</Chip>
            </div>
            <p className="text-sm text-[#9CA3AF] mb-4">Overall mastery and current focus areas.</p>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[#9CA3AF]">Overall mastery</p>
                <p className="text-3xl" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                  {studentOverview?.mastery?.overall != null ? `${studentOverview.mastery.overall}%` : "--"}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[#9CA3AF]">Confidence</p>
                <p className="text-sm font-semibold">{studentOverview?.confidence?.label || "Unknown"}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              {(studentOverview?.mastery?.weak || []).slice(0, 3).map((c: any) => (
                <span key={c.concept} className="text-xs px-3 py-1 rounded-full bg-[#F97316]/10 text-[#F97316]">
                  {c.concept}
                </span>
              ))}
            </div>
          </Card>
          <Card>
            <h3 className="text-lg font-semibold mb-2">Recommended Revision Plan</h3>
            <p className="text-sm text-[#9CA3AF] mb-3">Focus on one concept at a time for best gains.</p>
            <div className="space-y-2">
              {(studentOverview?.mastery?.weak || []).slice(0, 3).map((c: any, idx: number) => (
                <div key={`${c.concept}-${idx}`} className="flex items-center justify-between glass rounded-xl p-3">
                  <div>
                    <p className="text-sm font-semibold">{c.concept}</p>
                    <p className="text-xs text-[#9CA3AF]">{c.avg_mastery}% mastery</p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      localStorage.setItem("icodex.practice.prefill", JSON.stringify({ topic: c.concept }));
                      showToast("Open Practice to start this focus session.", "info");
                    }}
                  >
                    Practice
                  </Button>
                </div>
              ))}
              {(studentOverview?.mastery?.weak || []).length === 0 && (
                <p className="text-sm text-[#9CA3AF]">No weak concepts yet. Keep practicing!</p>
              )}
            </div>
          </Card>
        </div>
      )}

      {isStudent && (
        <div className="mb-8">
          <Card>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xl font-semibold">Progress Journey</h3>
              <Chip variant="info" size="sm">
                XP + Mastery
              </Chip>
            </div>
            <p className="text-sm text-[#9CA3AF] mb-3">
              Level {studentOverview?.gamification?.level || 1} • XP {studentOverview?.gamification?.xp_total || 0}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              {(studentOverview?.progress || []).slice(-5).map((day: any) => (
                <div key={day.date} className="text-center">
                  <div className="h-16 rounded-xl bg-[#E3EBFF] mb-1 relative overflow-hidden">
                    <div
                      className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#4169E1] to-[#7C3AED]"
                      style={{ height: `${Math.min(100, (day.mastery || 0) || 1)}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-[#9CA3AF]">{day.date.slice(5)}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-3 mb-8">
        <Card>
          <h3 className="text-lg font-semibold mb-2">Concept Mastery</h3>
          {insightsLoading ? (
            <p className="text-sm text-[#9CA3AF]">Loading concept signals...</p>
          ) : insights?.concept_mastery?.length ? (
            <div className="space-y-3">
              {insights.concept_mastery.slice(0, 6).map((concept: any) => (
                <div key={concept.concept} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span>{concept.concept}</span>
                    <span className="text-[#9CA3AF]">{concept.avg_mastery}%</span>
                  </div>
                  <div className="h-2 bg-[#E5E7EB] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#4169E1]"
                      style={{ width: `${Math.min(100, concept.avg_mastery)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">No concept mastery data yet.</p>
          )}
        </Card>

        <Card>
          <h3 className="text-lg font-semibold mb-2">Misconception Clusters</h3>
          {insightsLoading ? (
            <p className="text-sm text-[#9CA3AF]">Loading misconception clusters...</p>
          ) : insights?.misconceptions?.length ? (
            <div className="space-y-2">
              {insights.misconceptions.slice(0, 6).map((item: any) => (
                <div key={item.concept} className="flex items-center justify-between">
                  <span className="text-sm">{item.concept}</span>
                  <Chip variant="warning" size="sm">
                    {item.count} signals
                  </Chip>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">No misconception signals yet.</p>
          )}
        </Card>

        <Card>
          <h3 className="text-lg font-semibold mb-2">Behavior Signals</h3>
          {insightsLoading ? (
            <p className="text-sm text-[#9CA3AF]">Loading behavior insights...</p>
          ) : insights?.behavior ? (
            <div className="flex flex-wrap gap-2">
              <Chip variant="warning" size="sm">
                Guessing {insights.behavior.guessing || 0}
              </Chip>
              <Chip variant="error" size="sm">
                Confusion {insights.behavior.confusion || 0}
              </Chip>
              <Chip variant="success" size="sm">
                Steady {insights.behavior.steady || 0}
              </Chip>
              <Chip variant="info" size="sm">
                Fast Correct {insights.behavior.fast_correct || 0}
              </Chip>
              <Chip variant="secondary" size="sm">
                Slow Correct {insights.behavior.slow_correct || 0}
              </Chip>
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">No behavior insights yet.</p>
          )}
        </Card>
      </div>

      <div className="mb-6">
        <PillFilter filters={filters} activeFilter={filterType} onChange={setFilterType} />
      </div>

      <div className="grid gap-6">
        {loading && (
          <div className="grid gap-4">
            {[0, 1, 2].map((idx) => (
              <Card key={`report-skeleton-${idx}`}>
                <div className="animate-pulse space-y-4">
                  <div className="h-4 w-1/3 rounded-full bg-[#E3EBFF]/60" />
                  <div className="h-6 w-1/2 rounded-full bg-[#E3EBFF]/60" />
                  <div className="grid grid-cols-3 gap-3">
                    <div className="h-14 rounded-xl bg-[#E3EBFF]/60" />
                    <div className="h-14 rounded-xl bg-[#E3EBFF]/60" />
                    <div className="h-14 rounded-xl bg-[#E3EBFF]/60" />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
        {!loading && (filteredReports.length === 0 || emptyState) && (
          <Card>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h3 className="text-lg mb-1">No reports yet</h3>
                <p className="text-sm text-[#9CA3AF]">
                  Complete an assigned test or start a practice quiz to generate insights.
                </p>
              </div>
              <Button
                variant="secondary"
                icon={Sparkles}
                onClick={() => showToast("Open Practice to generate your first report.", "info")}
              >
                Start Practice
              </Button>
            </div>
          </Card>
        )}
        {filteredReports.map((report, index) => (
          <motion.div
            key={report.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card hover>
              <div className="flex flex-col lg:flex-row gap-6">
                {/* Report Info */}
                <div className="flex-1">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-xl mb-1">{report.title}</h3>
                      <p className="text-sm text-[#9CA3AF]">{report.date}</p>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-full text-sm ${
                        report.type === "test"
                          ? "bg-[#4169E1]/10 text-[#4169E1]"
                          : "bg-[#7C3AED]/10 text-[#7C3AED]"
                      }`}
                    >
                      {report.kind || report.type}
                    </span>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="glass rounded-xl p-3">
                      <p className="text-xs text-[#9CA3AF] mb-1">Score</p>
                      <p
                        className="text-2xl"
                        style={{
                          color: report.score >= 90 ? "#22C55E" : report.score >= 80 ? "#4169E1" : "#F97316",
                        }}
                      >
                        {report.score}%
                      </p>
                    </div>
                    <div className="glass rounded-xl p-3">
                      <p className="text-xs text-[#9CA3AF] mb-1">Questions</p>
                      <p className="text-2xl">{report.questions}</p>
                    </div>
                    <div className="glass rounded-xl p-3">
                      <p className="text-xs text-[#9CA3AF] mb-1">Time</p>
                      <p className="text-2xl">{report.timeSpent || 0}m</p>
                    </div>
                  </div>

                  {/* Strengths & Weaknesses */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-2">Strengths</p>
                      <div className="flex flex-wrap gap-1">
                        {(report.strengths || []).map((strength: string) => (
                          <span
                            key={strength}
                            className="px-2 py-1 rounded-full bg-[#22C55E]/10 text-[#22C55E] text-xs"
                          >
                            {strength}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-2">Areas to Improve</p>
                      <div className="flex flex-wrap gap-1">
                        {(report.weaknesses || []).length > 0 ? (
                          (report.weaknesses || []).map((weakness: string) => (
                            <span
                              key={weakness}
                              className="px-2 py-1 rounded-full bg-[#F97316]/10 text-[#F97316] text-xs"
                            >
                              {weakness}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-[#9CA3AF]">None - Great work!</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Mini Chart */}
                <div className="w-full lg:w-48 glass rounded-xl p-4 flex flex-col items-center justify-center">
                  <BarChart3 size={48} className="text-[#4169E1] mb-2" />
                  <p className="text-xs text-[#9CA3AF] text-center mb-3">Performance Breakdown</p>
                  <div className="flex gap-2 w-full">
                    {(() => {
                      const baseId = report.testId || report.id;
                      const allowDelete = canDeleteReport(report);
                      const options = studentOptionsByTest[baseId] || [];
                      const hasTeacherView = isTeacherOrAdmin && options.length > 0;
                      const studentId = currentUser?.id;
                      const pdfHref = hasTeacherView
                        ? `/api/tests/${baseId}/mastery-report?student_id=${options[0].studentId}&format=pdf`
                        : studentId
                        ? `/api/tests/${baseId}/mastery-report?student_id=${studentId}&format=pdf`
                        : `/api/tests/${baseId}/quiz?format=pdf`;

                      return (
                        <>
                          <Button
                            variant="primary"
                            size="sm"
                            icon={Eye}
                            disabled={isTeacherOrAdmin && options.length === 0}
                            onClick={() => {
                              if (isStudent) {
                                openStudentDetail(report);
                              } else if (hasTeacherView) {
                                openMasteryModal(baseId, options[0].studentId);
                              } else if (studentId) {
                                window.open(`/api/tests/${baseId}/mastery-report?student_id=${studentId}&format=html`, "_blank");
                              } else {
                                window.open(`/api/tests/${baseId}/quiz`, "_blank");
                              }
                            }}
                          >
                            View
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            icon={Download}
                            disabled={isTeacherOrAdmin && options.length === 0}
                            asChild={!isTeacherOrAdmin || options.length === 0}
                            onClick={() => {
                              if (hasTeacherView) {
                                window.open(pdfHref, "_blank");
                              }
                            }}
                          >
                            {isTeacherOrAdmin && options.length > 0 ? (
                              <span>PDF</span>
                            ) : (
                              <a href={pdfHref} target="_blank" rel="noreferrer">
                                PDF
                              </a>
                            )}
                          </Button>
                          {allowDelete && (
                            <Button
                              variant="tertiary"
                              size="sm"
                              icon={Trash2}
                              disabled={!baseId || deleting === baseId}
                              onClick={() => deleteTest(baseId)}
                            >
                              {deleting === baseId ? "Deleting..." : "Delete"}
                            </Button>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        ))}

        {isTeacherOrAdmin && assignmentResults.length > 0 && (
          <Card>
            <h3 className="text-xl mb-4">Student Mastery Reports</h3>
            <div className="space-y-3">
              {assignmentResults.map((r, idx) => (
                <div key={idx} className="glass rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <p className="text-sm text-[#9CA3AF] mb-1">{r.testTitle}</p>
                    <p className="text-base">{r.studentName}</p>
                  </div>
                  <div className="flex flex-col md:flex-row gap-4 md:items-center">
                    <div className="text-right">
                      <p className="text-xs text-[#9CA3AF]">Score</p>
                      <p className="text-2xl">{r.percent != null ? `${r.percent}%` : "--"}</p>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Strengths</p>
                      <div className="flex flex-wrap gap-1">
                        {(r.strengths || []).map((s: string) => (
                          <span key={s} className="px-2 py-1 rounded-full bg-[#22C55E]/10 text-[#22C55E] text-xs">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Areas to Improve</p>
                      <div className="flex flex-wrap gap-1">
                        {(r.weaknesses || []).length > 0 ? (
                          (r.weaknesses || []).map((w: string) => (
                            <span key={w} className="px-2 py-1 rounded-full bg-[#F97316]/10 text-[#F97316] text-xs">
                              {w}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-[#9CA3AF]">None</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="primary" size="sm" icon={Eye} onClick={() => openMasteryModal(r.testId, r.studentId)}>
                      View
                    </Button>
                    <Button variant="secondary" size="sm" icon={Download} asChild>
                      <a
                        href={`/api/tests/${r.testId}/mastery-report?student_id=${r.studentId}&format=pdf`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        PDF
                      </a>
                    </Button>
                    {canDeleteTestId(r.testId) && (
                      <Button
                        variant="tertiary"
                        size="sm"
                        icon={Trash2}
                        disabled={!r.testId || deleting === r.testId}
                        onClick={() => deleteTest(r.testId)}
                      >
                        {deleting === r.testId ? "Deleting..." : "Delete"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      <Modal
        isOpen={masteryModalOpen}
        onClose={() => setMasteryModalOpen(false)}
        title="Mastery Report"
        description="Detailed student performance breakdown"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setMasteryModalOpen(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              icon={Download}
              disabled={!pdfLink}
              asChild
            >
              <a href={pdfLink || "#"} target="_blank" rel="noreferrer">
                Download PDF
              </a>
            </Button>
          </>
        }
      >
        {currentStudentOptions.length > 1 && (
          <div className="mb-4">
            <label className="text-xs text-[#9CA3AF] mb-1 block">Select student</label>
            <select
              className="w-full glass rounded-lg px-3 py-2 text-sm"
              value={selectedStudentId || currentStudentOptions[0]?.studentId}
              onChange={(e) => onStudentChange(e.target.value)}
            >
              {currentStudentOptions.map((opt) => (
                <option key={opt.studentId} value={opt.studentId}>
                  {opt.studentName || "Student"}
                </option>
              ))}
            </select>
          </div>
        )}

        {masteryLoading && <p className="text-sm text-[#9CA3AF]">Loading mastery data...</p>}

        {!masteryLoading && masteryData && (
          <div className="space-y-4">
            <div className="glass rounded-xl p-4">
              <p className="text-xs text-[#9CA3AF] mb-1">{masteryData?.test?.title}</p>
              <h4 className="text-lg mb-1">{masteryData?.student?.name || "Student"}</h4>
              <p className="text-xs text-[#9CA3AF]">
                Score: {masteryData?.percent != null ? `${masteryData.percent}%` : masteryData?.score ?? "--"} •
                Questions: {masteryData?.limit ?? masteryData?.questionLimit ?? masteryData?.questions ?? "--"}
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="glass rounded-xl p-4">
                <p className="text-xs text-[#9CA3AF] mb-2">Strengths</p>
                <div className="flex flex-wrap gap-2">
                  {(masteryData?.strengths || []).length > 0 ? (
                    (masteryData?.strengths || []).map((s: string) => (
                      <span key={s} className="px-2 py-1 rounded-full bg-[#22C55E]/10 text-[#22C55E] text-xs">
                        {s}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-[#9CA3AF]">No strengths identified yet.</span>
                  )}
                </div>
              </div>
              <div className="glass rounded-xl p-4">
                <p className="text-xs text-[#9CA3AF] mb-2">Areas to Improve</p>
                <div className="flex flex-wrap gap-2">
                  {(masteryData?.weaknesses || []).length > 0 ? (
                    (masteryData?.weaknesses || []).map((w: string) => (
                      <span key={w} className="px-2 py-1 rounded-full bg-[#F97316]/10 text-[#F97316] text-xs">
                        {w}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-[#9CA3AF]">No gaps detected yet.</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {!masteryLoading && !masteryData && (
          <p className="text-sm text-[#9CA3AF]">No mastery data available yet for this student.</p>
        )}
      </Modal>

      <Modal
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailReport?.title || "Report Details"}
        description="Concept mastery, misconceptions, and next steps."
        size="lg"
        footer={
          <>
            <Button variant="tertiary" onClick={() => setDetailOpen(false)}>
              Close
            </Button>
            {detailReport?.testId && (
              <Button variant="secondary" icon={Download} asChild>
                <a href={`/api/tests/${detailReport.testId}/quiz?format=pdf`} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
              </Button>
            )}
          </>
        }
      >
        {detailLoading && <p className="text-sm text-[#9CA3AF]">Loading report insights...</p>}

        {!detailLoading && detailReport && (
          <div className="space-y-4">
            <div className="glass rounded-xl p-4">
              <p className="text-xs text-[#9CA3AF] mb-1">{detailReport.date}</p>
              <h4 className="text-lg mb-1">{detailReport.title}</h4>
              <p className="text-xs text-[#9CA3AF]">
                Score: {detailReport.score ?? "--"}% - Questions: {detailReport.questions ?? "--"}
              </p>
              {studentOverview?.mastery?.overall != null && detailReport.score != null && (
                <p className="text-xs text-[#9CA3AF] mt-1">
                  Change vs overall: {detailReport.score - studentOverview.mastery.overall >= 0 ? "+" : ""}
                  {Math.round(detailReport.score - studentOverview.mastery.overall)} pts
                </p>
              )}
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="glass rounded-xl p-4">
                <p className="text-xs text-[#9CA3AF] mb-2">Concept Mastery</p>
                {detailInsights?.concept_mastery?.length ? (
                  <div className="space-y-2">
                    {detailInsights.concept_mastery.slice(0, 6).map((concept: any) => (
                      <div key={concept.concept} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>{concept.concept}</span>
                          <span className="text-[#9CA3AF]">{concept.avg_mastery}%</span>
                        </div>
                        <div className="h-2 bg-[#E5E7EB] rounded-full overflow-hidden">
                          <div className="h-full bg-[#4169E1]" style={{ width: `${concept.avg_mastery}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-[#9CA3AF]">No concept data yet.</p>
                )}
              </div>

              <div className="glass rounded-xl p-4">
                <p className="text-xs text-[#9CA3AF] mb-2">Misconceptions</p>
                {detailInsights?.misconceptions?.length ? (
                  <div className="space-y-2">
                    {detailInsights.misconceptions.slice(0, 6).map((item: any) => (
                      <div key={item.concept} className="flex items-center justify-between">
                        <span className="text-sm">{item.concept}</span>
                        <Chip variant="warning" size="sm">
                          {item.count} signals
                        </Chip>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-[#9CA3AF]">No misconception signals yet.</p>
                )}
              </div>
            </div>

            <div className="glass rounded-xl p-4">
              <p className="text-xs text-[#9CA3AF] mb-2">Recommended Next Steps</p>
              <div className="flex flex-wrap gap-2">
                {(detailMastery?.weaknesses || []).slice(0, 3).map((concept: string) => (
                  <Button
                    key={concept}
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      localStorage.setItem("icodex.practice.prefill", JSON.stringify({ topic: concept }));
                      showToast("Open Practice to focus on this concept.", "info");
                    }}
                  >
                    Practice {concept}
                  </Button>
                ))}
                {(detailMastery?.weaknesses || []).length === 0 && (
                  <span className="text-sm text-[#9CA3AF]">No weak concepts detected.</span>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
