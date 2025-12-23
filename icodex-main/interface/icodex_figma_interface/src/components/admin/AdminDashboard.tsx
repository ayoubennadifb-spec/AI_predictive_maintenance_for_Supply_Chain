import { motion } from "motion/react";
import { Users, GraduationCap, FileText, TrendingUp, Brain, AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Hero } from "../Hero";
import { StatCard } from "../Card";
import { api } from "../../utils/api";

export function AdminDashboard() {
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api<any>("/api/admin/overview");
        setOverview(data);
      } catch {
        setOverview(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const totals = overview?.totals || {};
  const mastery = overview?.mastery || {};
  const aiConfidence = overview?.ai_confidence || {};
  const pipeline = overview?.pipeline || {};
  const failedConcepts = overview?.most_failed_concepts || [];
  const recent = overview?.recent_activity || [];

  const confidencePercent = aiConfidence?.score != null ? Math.round(aiConfidence.score * 100) : null;
  const confidenceLabel = aiConfidence?.label || "Unknown";
  const atRiskCount = mastery?.at_risk_students ?? 0;
  const atRiskPercent = mastery?.at_risk_percent ?? 0;

  const badge = useMemo(() => {
    const failed = pipeline?.failed || 0;
    const pending = pipeline?.pending || 0;
    if (failed > 0) return { label: "Pipeline Attention Needed", variant: "warning" as const };
    if (pending > 0) return { label: "Pipeline Queue Active", variant: "info" as const };
    return { label: "AI Insights Live", variant: "success" as const };
  }, [pipeline?.failed, pipeline?.pending]);

  const stats = [
    {
      icon: Users,
      label: "Total Users",
      value: loading ? "..." : String(totals.users ?? 0),
      trend: { value: "Active accounts", positive: true },
      iconColor: "#4169E1",
    },
    {
      icon: GraduationCap,
      label: "Active Classes",
      value: loading ? "..." : String(totals.classes ?? 0),
      trend: { value: "Live cohorts", positive: true },
      iconColor: "#7C3AED",
    },
    {
      icon: FileText,
      label: "Tests Created",
      value: loading ? "..." : String(totals.tests ?? 0),
      trend: { value: "AI-generated", positive: true },
      iconColor: "#22C55E",
    },
    {
      icon: TrendingUp,
      label: "Ready Tests",
      value: loading ? "..." : String(totals.ready_tests ?? 0),
      trend: { value: "Approved", positive: true },
      iconColor: "#F97316",
    },
    {
      icon: Brain,
      label: "Avg Mastery",
      value: mastery?.average != null ? `${mastery.average}%` : "—",
      trend: { value: "Concept-level", positive: (mastery?.average ?? 0) >= 70 },
      iconColor: "#0EA5E9",
    },
    {
      icon: AlertTriangle,
      label: "At-Risk Students",
      value: `${atRiskCount}`,
      trend: { value: `${atRiskPercent}% of students`, positive: atRiskPercent < 20 },
      iconColor: "#EF4444",
    },
  ];

  const maxFailed = failedConcepts.reduce((max: number, c: any) => Math.max(max, c.failed || 0), 1);

  const formatActivity = (entry: any) => {
    const action = entry?.action || "activity";
    if (action === "test_approved") return "approved a test";
    if (action === "test_assigned") return "assigned a test";
    if (action === "user_created") return "created a user";
    if (action === "role_changed") return "changed a role";
    if (action === "status_changed") return "updated status";
    if (action === "test_deleted") return "deleted a test";
    return action.replace(/_/g, " ");
  };

  const gamification = overview?.gamification_metrics || {};
  const streakDistribution = gamification?.streak_distribution || {};

  return (
    <div>
      <Hero
        title="Admin Dashboard"
        description="AI visibility for mastery, risk, pipeline health, and concept coverage."
        badge={badge}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-lg">AI Reliability</h3>
            <span className="text-xs text-[#9CA3AF]">{confidenceLabel}</span>
          </div>
          <p className="text-3xl mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            {confidencePercent != null ? `${confidencePercent}%` : "—"}
          </p>
          <div className="h-2 bg-[#E3EBFF] rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-gradient-to-r from-[#4169E1] to-[#7C3AED]"
              style={{ width: `${confidencePercent ?? 0}%` }}
            />
          </div>
          <p className="text-xs text-[#9CA3AF]">
            Based on {aiConfidence?.samples ?? 0} evaluated answers
          </p>
        </div>

        <div className="glass rounded-2xl p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg">Most Failed Concepts (7d)</h3>
            <span className="text-xs text-[#9CA3AF]">Top blockers</span>
          </div>
          {failedConcepts.length === 0 ? (
            <p className="text-sm text-[#16A34A]">No recurring failures this week.</p>
          ) : (
            <div className="space-y-3">
              {failedConcepts.map((concept: any) => (
                <div key={concept.concept} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span>{concept.concept}</span>
                    <span className="text-xs text-[#9CA3AF]">{concept.failed} failures</span>
                  </div>
                  <div className="h-2 bg-[#E5E7EB] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#EF4444]"
                      style={{ width: `${Math.round((concept.failed / maxFailed) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="glass rounded-2xl p-6 mb-8">
        <h3 className="text-xl mb-2">Pipeline Health</h3>
        <p className="text-sm text-[#9CA3AF] mb-4">
          Pending and failed quiz runs with average processing time.
        </p>
        <div className="flex flex-wrap gap-4 text-sm mb-4">
          <span className="text-[#F97316] bg-[#F97316]/10 px-3 py-1 rounded-full">
            Pending: {pipeline?.pending ?? 0}
          </span>
          <span className="text-[#EF4444] bg-[#EF4444]/10 px-3 py-1 rounded-full">
            Failed: {pipeline?.failed ?? 0}
          </span>
          <span className="text-[#4169E1] bg-[#4169E1]/10 px-3 py-1 rounded-full">
            Avg Duration: {pipeline?.avg_duration_seconds ?? "--"}s
          </span>
        </div>
        {pipeline?.issues?.length ? (
          <div className="space-y-3">
            {pipeline.issues.map((issue: any) => (
              <div key={issue.test_id} className="glass rounded-xl p-4 bg-[#FFF7ED]">
                <p className="text-sm font-semibold">{issue.title}</p>
                <p className="text-xs text-[#9CA3AF]">
                  Stage: {issue.stage || "Pipeline"} · Status: {issue.status}
                </p>
                {issue.error && <p className="text-xs text-[#EF4444] mt-2">Error: {issue.error}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#16A34A]">All pipelines are healthy.</p>
        )}
      </div>

      <div className="glass rounded-2xl p-6 mb-8">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xl">Gamification Health</h3>
          <span className="text-xs text-[#9CA3AF]">Real-time engagement</span>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm mb-4">
          <div>
            <p className="text-xs text-[#9CA3AF]">Active (24h)</p>
            <p className="text-2xl">{gamification.daily_active_students ?? "--"}</p>
          </div>
          <div>
            <p className="text-xs text-[#9CA3AF]">Avg XP/day</p>
            <p className="text-2xl">{gamification.avg_xp_per_day ?? "--"}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-[#475569] mb-3">
          {Object.entries(streakDistribution).map(([label, value]) => (
            <span key={label} className="px-3 py-1 rounded-full bg-[#E3EBFF]/30">
              {label}: {value}
            </span>
          ))}
        </div>
        <p className="text-xs text-[#9CA3AF]">
          Quests completed (7d): {gamification.quests_completed_last_week ?? 0}
        </p>
      </div>

      <div className="glass rounded-2xl p-6">
        <h3 className="text-xl mb-4">Recent Activity</h3>
        <div className="space-y-3">
          {recent.length === 0 ? (
            <p className="text-sm text-[#9CA3AF]">No admin actions logged yet.</p>
          ) : (
            recent.map((activity: any, index: number) => (
              <motion.div
                key={activity.id || index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className="flex items-center justify-between p-4 rounded-xl hover:bg-[#E3EBFF]/30 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center bg-[#4169E1]/10 text-[#4169E1]">
                    {String(activity.actor || "A").charAt(0)}
                  </div>
                  <div>
                    <p className="text-sm">
                      <span>{activity.actor || "System"}</span>{" "}
                      <span className="text-[#9CA3AF]">{formatActivity(activity)}</span>
                    </p>
                    <p className="text-xs text-[#9CA3AF]">{activity.created_at || ""}</p>
                  </div>
                </div>
                <div className="text-xs px-2 py-1 rounded-full bg-[#E3EBFF]/40 text-[#4169E1]">
                  {activity.target_type || "system"}
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
