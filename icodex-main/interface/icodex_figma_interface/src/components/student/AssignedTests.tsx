import { useEffect, useMemo, useState } from "react";
import { Play, Target, Sparkles } from "lucide-react";
import { Hero } from "../Hero";
import { Card } from "../Card";
import { Button } from "../Button";
import { StatusChip } from "../Chip";
import { PillFilter } from "../Tabs";
import { motion } from "motion/react";
import { api } from "../../utils/api";
import { useToast } from "../Toast";

interface AssignedTestsProps {
  onStartTest: (assignmentId: string) => void;
  onViewReports: () => void;
}

export function AssignedTests({ onStartTest, onViewReports }: AssignedTestsProps) {
  const [filterStatus, setFilterStatus] = useState("all");
  const [tests, setTests] = useState<any[]>([]);
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();

  const fetchAssignments = async () => {
    try {
      const data = await api<{ assignments: any[] }>('/api/assignments/my-assignments');
      const mapped = (data.assignments || []).map((a: any) => {
        const quality = a.test?.quality || {};
        const conceptDist = quality.concept_distribution || {};
        const conceptList = Object.entries(conceptDist)
          .sort((first: any, second: any) => second[1] - first[1])
          .slice(0, 3)
          .map(([concept]) => concept);
        const fallbackConcepts = Array.isArray(a.concepts) ? a.concepts : [];
        const questions = a.test?.questionLimit || a.test?.limit || 0;
        const estimatedMinutes = questions ? Math.max(5, Math.round((questions * 20) / 60)) : 0;
        const rawStatus = (a.status || "").toLowerCase();
        let status: string;
        if (rawStatus === "completed") status = "completed";
        else if (rawStatus === "in_progress") status = "in_progress";
        else status = "not_started"; // map pending / anything else to not_started
        return {
          id: a.id || a.assignment_id,
          testId: a.test?.id || a.test_id,
          title: a.test?.title || 'Test',
          class: a.class_name || a.class || a.class_id || 'Class',
          teacher: a.test?.ownerName || a.test?.owner || 'Teacher',
          dueDate: a.dueDate || a.createdAt || '',
          status,
          questions,
          estimatedMinutes,
          timeLimit: a.test?.timeLimit || 0,
          description: a.test?.comment || '',
          score: a.finalScore,
          progress: a.progress,
          ready: a.ready !== false,
          error: a.error,
          concepts: conceptList.length > 0 ? conceptList : fallbackConcepts,
        };
      });
      setTests(mapped);
    } catch (err: any) {
      showToast(err?.message || "Failed to load assignments", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssignments();
    api<any>("/api/student/overview")
      .then((res) => setOverview(res))
      .catch(() => setOverview(null));
  }, []);

  const filteredTests = tests.filter(
    (test) => filterStatus === "all" || test.status === filterStatus
  );

  const focusConcepts = useMemo(() => {
    const weak = overview?.mastery?.weak || [];
    return weak.slice(0, 3);
  }, [overview]);

  const statusFilters = [
    { id: "all", label: "All" },
    { id: "not_started", label: "Not Started" },
    { id: "in_progress", label: "In Progress" },
    { id: "completed", label: "Completed" },
  ];

  return (
    <div>
      <Hero
        title="Assigned Tests"
        description="View and take tests assigned by your teachers"
        badge={{
          label: `${tests.filter((t) => t.status !== "completed").length} active tests`,
          variant: "info",
        }}
      />

      <div className="glass rounded-2xl p-4 mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">AI Focus for You</p>
          <p className="text-xs text-[#9CA3AF]">Based on recent mistakes and mastery.</p>
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

      <div className="mb-6">
        <PillFilter
          filters={statusFilters}
          activeFilter={filterStatus}
          onChange={setFilterStatus}
        />
      </div>

      <div className="grid gap-6">
        {loading && (
          <Card>
            <div className="animate-pulse space-y-4">
              <div className="h-4 w-1/3 rounded-full bg-[#E3EBFF]/60" />
              <div className="h-6 w-1/2 rounded-full bg-[#E3EBFF]/60" />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="h-10 rounded-xl bg-[#E3EBFF]/60" />
                <div className="h-10 rounded-xl bg-[#E3EBFF]/60" />
                <div className="h-10 rounded-xl bg-[#E3EBFF]/60" />
                <div className="h-10 rounded-xl bg-[#E3EBFF]/60" />
              </div>
            </div>
          </Card>
        )}
        {!loading && filteredTests.length === 0 && (
          <Card>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h3 className="text-lg mb-1">No assigned tests yet</h3>
                <p className="text-sm text-[#9CA3AF]">
                  Ask your teacher to assign a test or join a class to get started.
                </p>
              </div>
              <Button
                variant="secondary"
                icon={Sparkles}
                onClick={() => showToast("Request sent to your teacher (demo).", "info")}
              >
                Request Test
              </Button>
            </div>
          </Card>
        )}
        {filteredTests.map((test, index) => (
          <motion.div
            key={test.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card hover>
              <div className="flex flex-col lg:flex-row lg:items-start gap-6">
                {/* Test Info */}
                <div className="flex-1">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-xl mb-1">{test.title}</h3>
                      <p className="text-[#9CA3AF]">{test.description}</p>
                    </div>
                    <StatusChip status={test.status} />
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Class</p>
                      <p className="text-sm">{test.class}</p>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Teacher</p>
                      <p className="text-sm">{test.teacher}</p>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Questions</p>
                      <p className="text-sm">{test.questions}</p>
                    </div>
                    <div>
                      <p className="text-xs text-[#9CA3AF] mb-1">Est. Time</p>
                      <p className="text-sm">{test.estimatedMinutes} min</p>
                    </div>
                  </div>

                  {test.concepts?.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {test.concepts.map((concept: string) => (
                        <span key={concept} className="text-xs px-3 py-1 rounded-full bg-[#4169E1]/10 text-[#4169E1]">
                          {concept}
                        </span>
                      ))}
                    </div>
                  )}

                  {test.status === "in_progress" && test.progress && (
                    <div className="mb-4">
                      <div className="flex justify-between items-center mb-2">
                        <p className="text-sm text-[#475569]">Progress</p>
                        <p className="text-sm text-[#4169E1]">{test.progress}%</p>
                      </div>
                      <div className="h-2 bg-[#E3EBFF] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-[#4169E1] to-[#7C3AED]"
                          style={{ width: `${test.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {test.status === "completed" && test.score !== undefined && (
                    <div className="glass rounded-xl p-4 bg-[#22C55E]/5 inline-block">
                      <p className="text-sm text-[#9CA3AF] mb-1">Your Score</p>
                      <p className="text-3xl text-[#22C55E]">{test.score}%</p>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex flex-col gap-2 lg:w-48">
                  {test.status === "not_started" && (
                    <>
                      <Button
                        variant="primary"
                        icon={Play}
                        disabled={test.ready === false}
                        onClick={() => onStartTest(test.id)}
                      >
                        {test.ready === false ? "Not Ready" : "Start Test"}
                      </Button>
                      <p className="text-xs text-[#9CA3AF] text-center">Due: {test.dueDate}</p>
                      {test.ready === false && (
                        <p className="text-xs text-[#F97316] text-center">{test.error || "Quiz not ready yet."}</p>
                      )}
                    </>
                  )}
                  {test.status === "in_progress" && (
                    <>
                      <Button
                        variant="primary"
                        icon={Target}
                        disabled={test.ready === false}
                        onClick={() => onStartTest(test.id)}
                      >
                        {test.ready === false ? "Not Ready" : "Continue"}
                      </Button>
                      <p className="text-xs text-[#F97316] text-center">Due: {test.dueDate}</p>
                      {test.ready === false && (
                        <p className="text-xs text-[#F97316] text-center">{test.error || "Quiz not ready yet."}</p>
                      )}
                    </>
                  )}
                  {test.status === "completed" && (
                    <Button variant="secondary" onClick={onViewReports}>
                      Review
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
