import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Upload, Sparkles, FileText, BarChart3, AlertTriangle, Brain, Flame } from "lucide-react";
import { Hero } from "../Hero";
import { StatCard, Card } from "../Card";
import { Button } from "../Button";
import { api } from "../../utils/api";
import { Chip } from "../Chip";
import { useToast } from "../Toast";
import { Input } from "../Input";
import { Modal } from "../Modal";
import { ProgressBar } from "../ProgressBar";

interface TeacherDashboardProps {
  onNavigate: (page: string) => void;
}

interface Stat {
  icon: any;
  label: string;
  value: string;
  trend?: { value: string; positive: boolean };
  iconColor: string;
}

export function TeacherDashboard({ onNavigate }: TeacherDashboardProps) {
  const { showToast } = useToast();
  const [stats, setStats] = useState<Stat[]>([
    {
      icon: FileText,
      label: "Tests Created",
      value: "0",
      trend: { value: "", positive: true },
      iconColor: "#4169E1",
    },
    {
      icon: Sparkles,
      label: "Tests Processing",
      value: "0",
      iconColor: "#F97316",
    },
    {
      icon: FileText,
      label: "Tests Ready",
      value: "0",
      iconColor: "#22C55E",
    },
    {
      icon: BarChart3,
      label: "Avg. Student Score",
      value: "--",
      trend: { value: "", positive: true },
      iconColor: "#7C3AED",
    },
  ]);

  const [recentTests, setRecentTests] = useState<any[]>([]);
  const [processingBadge, setProcessingBadge] = useState<string | null>(null);
  const [classHealth, setClassHealth] = useState<any[]>([]);
  const [weakConcepts, setWeakConcepts] = useState<any[]>([]);
  const [misconceptions, setMisconceptions] = useState<any[]>([]);
  const [testsAttention, setTestsAttention] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [engagement, setEngagement] = useState<any>(null);
  const [teacherClasses, setTeacherClasses] = useState<any[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [leaderboardData, setLeaderboardData] = useState<any>(null);
  const [leaderboardConfig, setLeaderboardConfig] = useState<any>(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardUpdating, setLeaderboardUpdating] = useState(false);
  const [classQuests, setClassQuests] = useState<any[]>([]);
  const [questModalOpen, setQuestModalOpen] = useState(false);
  const [questForm, setQuestForm] = useState({ title: "", concept: "", target: "5", reward: "30" });
  const [questSubmitting, setQuestSubmitting] = useState(false);
  const [classesLoading, setClassesLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const my = await api<{ tests: any[] }>("/api/tests/my-tests");
        const tests = my.tests || [];

        const totalTests = tests.length;
        const readyTests = tests.filter(
          (t) => (t.status || "").toLowerCase() === "ready"
        ).length;
        const processingTests = tests.filter((t) =>
          (t.status || "").toLowerCase().startsWith("processing")
        ).length;

        const assignmentRes = await api<{ assignments: any[] }>(
          "/api/assignments/results"
        ).catch(() => ({ assignments: [] }));

        let percentSum = 0;
        let percentCount = 0;
        (assignmentRes.assignments || []).forEach((a: any) => {
          (a.results || []).forEach((r: any) => {
            if (typeof r.percent === "number") {
              percentSum += r.percent;
              percentCount += 1;
            }
          });
        });
        const avgScore =
          percentCount > 0 ? Math.round(percentSum / percentCount) : null;

        setStats([
          {
            icon: FileText,
            label: "Tests Created",
            value: String(totalTests),
            trend: { value: "", positive: true },
            iconColor: "#4169E1",
          },
          {
            icon: Sparkles,
            label: "Tests Processing",
            value: String(processingTests),
            iconColor: "#F97316",
          },
          {
            icon: FileText,
            label: "Tests Ready",
            value: String(readyTests),
            iconColor: "#22C55E",
          },
          {
            icon: BarChart3,
            label: "Avg. Student Score",
            value: avgScore != null ? `${avgScore}%` : "--",
            trend: { value: "", positive: true },
            iconColor: "#7C3AED",
          },
        ]);

        // class health
        api<any>("/api/classes/health")
          .then((res) => {
            const list = Object.entries(res.classes || {}).map(([id, row]: any) => ({
              id,
              name: row?.name || id,
              avgMastery: row?.avg_mastery,
              struggling: row?.struggling_percent,
              lastActive: row?.last_activity_at,
              students: row?.students,
            }));
            setClassHealth(list);
          })
          .catch(() => setClassHealth([]));

        // insights
        let insightsConcepts: any[] = [];
        api<any>("/api/reports/insights")
          .then((res) => {
            insightsConcepts = res?.concept_mastery || [];
            setWeakConcepts(insightsConcepts);
            setMisconceptions(res?.misconceptions || []);
          })
          .catch(() => {
            insightsConcepts = [];
            setWeakConcepts([]);
            setMisconceptions([]);
          });

        // tests needing attention
        const attention = tests.filter((t) => {
          const status = String(t.status || "").toLowerCase();
          const qualityScore = t.quality?.quality_score;
          return status.startsWith("failed") || status.startsWith("pending") || (qualityScore != null && qualityScore < 70);
        });
        setTestsAttention(attention);

        // suggestions
        setTimeout(() => {
          const sugg: any[] = [];
          const weakest = (insightsConcepts || []).slice(0, 3);
          weakest.forEach((c: any) => {
            sugg.push({
              label: `Assign practice on ${c.concept}`,
              reason: `${c.avg_mastery}% mastery`,
              action: () => onNavigate("tests"),
            });
          });
          if (attention.length > 0) {
            sugg.push({
              label: "Review tests needing attention",
              reason: `${attention.length} test(s) pending/low quality`,
              action: () => onNavigate("tests"),
            });
          }
          setSuggestions(sugg);
        }, 100);

        if (processingTests > 0) {
          setProcessingBadge(
            `${processingTests} test${processingTests > 1 ? "s" : ""} processing`
          );
        } else {
          setProcessingBadge(null);
        }

        const latest = tests
          .slice(-3)
          .reverse()
          .map((t) => ({
            title: t.title || "Untitled Test",
            status: (t.status || "").toLowerCase(),
            questions: t.questionLimit || t.limit || 0,
            date: t.createdAt || t.created_at || "",
          }));
        setRecentTests(latest);
        const engagementRes = await api<any>("/api/teacher/engagement").catch(() => null);
        if (engagementRes) {
          setEngagement(engagementRes);
        }
      } catch {
        showToast("Failed to load dashboard data", "error");
      }
      setLoading(false);
    };

    load();
  }, []);

  useEffect(() => {
    const fetchClasses = async () => {
      setClassesLoading(true);
      try {
        const me = await api<{ user: any }>("/api/auth/me");
        const classesRes = await api<{ classes: any[] }>("/api/classes");
        const teacherId = me?.user?.id;
        const filtered = (classesRes?.classes || []).filter(
          (cls) => Array.isArray(cls?.teachers) && cls.teachers.includes(teacherId)
        );
        setTeacherClasses(filtered);
        setSelectedClassId((prev) => prev || (filtered[0]?.id ?? null));
      } catch {
        setTeacherClasses([]);
      } finally {
        setClassesLoading(false);
      }
    };
    fetchClasses();
  }, []);

  const loadLeaderboardForClass = async (classId: string) => {
    setLeaderboardLoading(true);
    try {
      const data = await api<any>(`/api/classes/${classId}/leaderboard`);
      setLeaderboardData(data);
      setLeaderboardConfig(data.config);
    } catch (err: any) {
      showToast(err?.message || "Failed to load leaderboard", "error");
    } finally {
      setLeaderboardLoading(false);
    }
  };

  const loadQuestsForClass = async (classId: string) => {
    try {
      const res = await api<any>(`/api/quests?class_id=${classId}`);
      setClassQuests(res?.quests || []);
    } catch {
      setClassQuests([]);
    }
  };

  const refreshClassData = (classId: string) => {
    loadLeaderboardForClass(classId);
    loadQuestsForClass(classId);
  };

  useEffect(() => {
    if (!selectedClassId) {
      return;
    }
    refreshClassData(selectedClassId);
  }, [selectedClassId]);

  const updateLeaderboardConfig = async (updates: Record<string, any>) => {
    if (!selectedClassId) return;
    setLeaderboardUpdating(true);
    try {
      const res = await api<any>(`/api/classes/${selectedClassId}/leaderboard`, {
        method: "PUT",
        body: JSON.stringify(updates),
      });
      setLeaderboardData(res);
      setLeaderboardConfig(res.config);
    } catch (err: any) {
      showToast(err?.message || "Failed to update leaderboard", "error");
    } finally {
      setLeaderboardUpdating(false);
    }
  };

  const handleQuestCreate = async () => {
    if (!selectedClassId) {
      showToast("Select a class before creating a quest", "error");
      return;
    }
    const concept = questForm.concept?.trim();
    if (!concept) {
      showToast("Enter a focus concept", "error");
      return;
    }
    setQuestSubmitting(true);
    try {
      await api(`/api/teacher/classes/${selectedClassId}/quests`, {
        method: "POST",
        body: JSON.stringify({
        title: questForm.title || `Reinforce ${concept}`,
        description: `Practice ${concept} questions.`,
        criteria: {
          type: "concept",
          concept,
          target: Math.max(1, Number(questForm.target) || 5),
        },
          reward_xp: Math.max(5, Number(questForm.reward) || 30),
        }),
      });
      showToast("Quest created", "success");
      setQuestModalOpen(false);
      setQuestForm({ title: "", concept: "", target: "5", reward: "30" });
      refreshClassData(selectedClassId);
    } catch (err: any) {
      showToast(err?.message || "Failed to create quest", "error");
    } finally {
      setQuestSubmitting(false);
    }
  };

  const quickActions = [
    {
      title: "Quiz Studio",
      description: "Upload PDFs and generate adaptive quizzes with AI",
      icon: Sparkles,
      color: "#4169E1",
      action: () => onNavigate("studio"),
    },
    {
      title: "My Tests",
      description: "View and manage all your created tests",
      icon: FileText,
      color: "#7C3AED",
      action: () => onNavigate("tests"),
    },
    {
      title: "Reports",
      description: "Analyze student performance and progress",
      icon: BarChart3,
      color: "#22C55E",
      action: () => onNavigate("reports"),
    },
  ];

  return (
    <div>
      <Hero
        title="Teaching Intelligence"
        description="See class health, misconceptions, and AI actions before you grade."
        primaryAction={{
          label: "Upload New Test",
          icon: Upload,
          onClick: () => onNavigate("studio"),
        }}
        badge={
          processingBadge
            ? { label: processingBadge, variant: "warning" }
            : undefined
        }
      />

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>

      <Card className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xl">Class Engagement</h3>
          <Chip variant="info" size="sm">
            XP Signals
          </Chip>
        </div>
        {engagement ? (
          <div className="grid md:grid-cols-3 gap-4 text-sm text-[#475569]">
            <div>
              <p className="text-xs text-[#9CA3AF]">Students</p>
              <p className="text-2xl">{engagement.students || 0}</p>
            </div>
            <div>
              <p className="text-xs text-[#9CA3AF]">Avg XP/day</p>
              <p className="text-2xl">{engagement.avg_xp_per_day}</p>
            </div>
            <div>
              <p className="text-xs text-[#9CA3AF]">Streak participation</p>
              <p className="text-2xl">{engagement.streak_participation}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-[#9CA3AF]">Loading engagement data...</p>
        )}
      </Card>

      {/* Class Health */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr,0.8fr] gap-6 mb-8">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Class Health</h3>
            <Chip variant="info" size="sm">AI Summary</Chip>
          </div>
          {loading ? (
            <p className="text-sm text-[#9CA3AF]">Loading...</p>
          ) : classHealth.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No classes yet. Create a class and assign a quiz.</p>
          ) : (
            <div className="grid md:grid-cols-2 gap-3">
              {classHealth.map((cls) => (
                <div key={cls.id} className="glass rounded-xl p-4">
                  <div className="flex items-center justify-between mb-1">
                    <p className="font-semibold">{cls.name || "Class"}</p>
                    <Chip variant={cls.avgMastery >= 75 ? "success" : cls.avgMastery >= 60 ? "warning" : "error"} size="sm">
                      {cls.avgMastery != null ? `${cls.avgMastery}%` : "--"}
                    </Chip>
                  </div>
                  <p className="text-xs text-[#9CA3AF]">At risk: {cls.struggling ?? 0}%</p>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Recent Misconceptions</h3>
            <AlertTriangle className="text-[#F97316]" size={18} />
          </div>
          {misconceptions.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No misconception signals yet.</p>
          ) : (
            <div className="space-y-2">
              {misconceptions.slice(0, 5).map((m: any) => (
                <div key={m.concept} className="flex items-center justify-between glass rounded-lg p-3">
                  <div>
                    <p className="text-sm font-semibold">{m.concept}</p>
                    <p className="text-xs text-[#9CA3AF]">{m.count} signals</p>
                  </div>
                  <Chip variant="warning" size="sm">{m.count}</Chip>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Weak Concepts + Suggestions */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr,0.9fr] gap-6 mb-8">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Top Weak Concepts</h3>
            <Brain className="text-[#4169E1]" size={18} />
          </div>
          {weakConcepts.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No weak concepts yet. Assign a quiz to see mastery.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {weakConcepts.slice(0, 8).map((c: any) => (
                <Chip key={c.concept} variant="warning" size="sm">
                  {c.concept} ({c.avg_mastery}%)
                </Chip>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Suggested Actions</h3>
            <Flame className="text-[#F97316]" size={18} />
          </div>
          {suggestions.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No actions yet. Generate or assign a quiz to unlock recommendations.</p>
          ) : (
            <div className="space-y-3">
              {suggestions.map((s: any, idx: number) => (
                <div key={idx} className="glass rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold">{s.label}</p>
                    <p className="text-xs text-[#9CA3AF]">{s.reason}</p>
                  </div>
                  <Button variant="secondary" size="sm" onClick={s.action || (() => onNavigate("tests"))}>
                    Go
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr,0.9fr] gap-6 mb-8">
        <Card>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-xl">Class Leaderboards</h3>
              <p className="text-sm text-[#9CA3AF]">
                XP, streaks, and mastery trends at a glance.
              </p>
            </div>
            <Chip variant="info" size="sm">
              {leaderboardData?.enabled ? "Live" : "Paused"}
            </Chip>
          </div>
          <div className="space-y-3 mb-4">
            <div>
              <p className="text-xs text-[#9CA3AF] mb-1">Class</p>
              {classesLoading ? (
                <p className="text-xs text-[#9CA3AF]">Loading classes...</p>
              ) : teacherClasses.length === 0 ? (
                <p className="text-xs text-[#9CA3AF]">No classes found.</p>
              ) : (
                <select
                  value={selectedClassId || ""}
                  onChange={(e) => setSelectedClassId(e.target.value)}
                  className="w-full border border-[#E2E8F0] rounded-xl px-3 py-2 text-sm"
                >
                  {teacherClasses.map((cls) => (
                    <option key={cls.id} value={cls.id}>
                      {cls.name || cls.id}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={leaderboardConfig?.enabled ? "secondary" : "primary"}
                size="sm"
                onClick={() =>
                  updateLeaderboardConfig({ enabled: !leaderboardConfig?.enabled })
                }
                disabled={leaderboardUpdating}
              >
                {leaderboardConfig?.enabled ? "Disable" : "Enable"} leaderboard
              </Button>
              <Button
                variant={leaderboardConfig?.anonymous ? "secondary" : "primary"}
                size="sm"
                onClick={() =>
                  updateLeaderboardConfig({ anonymous: !leaderboardConfig?.anonymous })
                }
                disabled={leaderboardUpdating}
              >
                {leaderboardConfig?.anonymous ? "Reveal names" : "Anonymous mode"}
              </Button>
              <Button
                variant={leaderboardConfig?.show_top_improvers ? "secondary" : "primary"}
                size="sm"
                onClick={() =>
                  updateLeaderboardConfig({
                    show_top_improvers: !leaderboardConfig?.show_top_improvers,
                  })
                }
                disabled={leaderboardUpdating}
              >
                {leaderboardConfig?.show_top_improvers ? "All entries" : "Top improvers"}
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#9CA3AF]">Focus</span>
              <select
                value={leaderboardConfig?.focus || "xp"}
                onChange={(e) => updateLeaderboardConfig({ focus: e.target.value })}
                className="border border-[#E2E8F0] rounded-xl px-3 py-2 text-sm"
                disabled={leaderboardUpdating}
              >
                <option value="xp">XP leaderboard</option>
                <option value="improvement">Improvement-focused</option>
              </select>
            </div>
          </div>
          {leaderboardLoading ? (
            <div className="space-y-3">
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
            </div>
          ) : !selectedClassId ? (
            <p className="text-sm text-[#9CA3AF]">Select a class to view the leaderboard.</p>
          ) : leaderboardData?.entries?.length ? (
            <div className="space-y-3">
              {leaderboardData.entries.map((row: any) => (
                <div key={row.student_id} className="glass rounded-xl p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold">
                        #{row.rank} {row.label}
                      </p>
                      <p className="text-xs text-[#9CA3AF]">Level {row.level}</p>
                    </div>
                    <Chip variant="success" size="xs">
                      {row.streak}d streak
                    </Chip>
                  </div>
                  <div className="flex flex-wrap gap-3 text-[11px] text-[#475569] mt-2">
                    <span>{row.xp_total} XP</span>
                    <span>+{row.weekly_xp ?? 0} this week</span>
                    <span>Δ {row.mastery_delta ?? "—"}%</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">No leaderboard data collected yet.</p>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-xl">Class Quests</h3>
              <p className="text-sm text-[#9CA3AF]">AI missions + teacher-created quests.</p>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setQuestModalOpen(true)}
              disabled={!selectedClassId}
            >
              Create quest
            </Button>
          </div>
          {!selectedClassId ? (
            <p className="text-sm text-[#9CA3AF]">Select a class to manage quests.</p>
          ) : classQuests.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No quests yet for this class.</p>
          ) : (
            <div className="space-y-3">
              {classQuests.map((quest) => (
                <div key={quest.id} className="glass rounded-xl p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold">{quest.title}</p>
                      <p className="text-xs text-[#9CA3AF]">{quest.description}</p>
                    </div>
                    <Chip variant="secondary" size="xs">
                      {quest.auto ? "AI" : "Teacher"}
                    </Chip>
                  </div>
                  <ProgressBar progress={Math.min(100, quest.progress_percent || 0)} showLabel={false} />
                  <div className="flex justify-between text-[11px] text-[#9CA3AF]">
                    <span>{quest.progress_percent ?? 0}% done</span>
                    <span>{quest.target} targets</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h3 className="text-xl mb-4">Quick Actions</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {quickActions.map((action, index) => {
            const Icon = action.icon;
            return (
              <motion.div
                key={action.title}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <Card hover onClick={action.action}>
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center mb-4"
                    style={{
                      background: `linear-gradient(135deg, ${action.color}20, ${action.color}10)`,
                    }}
                  >
                    <Icon size={24} style={{ color: action.color }} />
                  </div>
                  <h4 className="text-lg mb-2">{action.title}</h4>
                  <p className="text-sm text-[#9CA3AF] mb-4">
                    {action.description}
                  </p>
                  <Button variant="tertiary" size="sm">
                    Go to {action.title}
                  </Button>
                </Card>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Recent Tests */}
      <Card>
        <h3 className="text-xl mb-4">Recent Tests</h3>
        {recentTests.length === 0 ? (
          <p className="text-sm text-[#9CA3AF]">
            No tests yet. Create one in Quiz Studio.
          </p>
        ) : (
          <div className="space-y-3">
            {recentTests.map((test, index) => (
              <motion.div
                key={`${test.title}-${index}`}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                className="flex items-center justify-between p-4 rounded-xl hover:bg-[#E3EBFF]/30 transition-colors cursor-pointer"
              >
                <div>
                  <p className="mb-1">{test.title}</p>
                  <p className="text-sm text-[#9CA3AF]">
                    {test.questions} questions • {test.date}
                  </p>
                </div>
                <div
                  className={`px-3 py-1 rounded-full text-sm ${
                    test.status === "ready"
                      ? "bg-[#22C55E]/10 text-[#22C55E]"
                      : test.status.startsWith("processing") ||
                        test.status.startsWith("pending")
                      ? "bg-[#F97316]/10 text-[#F97316]"
                      : "bg-[#9CA3AF]/10 text-[#9CA3AF]"
                  }`}
                >
                  {test.status || "unknown"}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </Card>
      <Modal
        isOpen={questModalOpen}
        onClose={() => setQuestModalOpen(false)}
        title="Create a Class Quest"
        description="Reward students for practicing critical concepts."
        footer={
          <div className="flex justify-end gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setQuestModalOpen(false)}
              disabled={questSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleQuestCreate}
              disabled={questSubmitting}
            >
              {questSubmitting ? "Creating..." : "Create quest"}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input
            label="Quest title"
            value={questForm.title}
            onChange={(e) => setQuestForm((prev) => ({ ...prev, title: e.target.value }))}
            helperText="Optional custom title for the quest card."
          />
          <Input
            label="Focus concept"
            value={questForm.concept}
            onChange={(e) => setQuestForm((prev) => ({ ...prev, concept: e.target.value }))}
            helperText="Students will practice this topic."
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Target hits"
              type="number"
              min={1}
              value={questForm.target}
              onChange={(e) => setQuestForm((prev) => ({ ...prev, target: e.target.value }))}
            />
            <Input
              label="XP reward"
              type="number"
              min={5}
              value={questForm.reward}
              onChange={(e) => setQuestForm((prev) => ({ ...prev, reward: e.target.value }))}
              helperText="Bonus XP for completion."
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

