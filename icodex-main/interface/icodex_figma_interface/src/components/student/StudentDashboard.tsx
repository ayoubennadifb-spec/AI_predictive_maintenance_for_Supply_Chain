import { useEffect, useMemo, useState } from "react";
import { BookOpen, Target, Sparkles, Flame, Brain } from "lucide-react";
import { Hero } from "../Hero";
import { Card } from "../Card";
import { Button } from "../Button";
import { Chip } from "../Chip";
import { api } from "../../utils/api";
import { useToast } from "../Toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { ProgressBar } from "../ProgressBar";

interface StudentDashboardProps {
  onNavigate: (page: string) => void;
  onStartTest: (assignmentId: string) => void;
  onStartPractice?: (testId: string) => void;
}

export function StudentDashboard({ onNavigate, onStartTest, onStartPractice }: StudentDashboardProps) {
  const { showToast } = useToast();
  const [overview, setOverview] = useState<any>(null);
  const [plan, setPlan] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [quests, setQuests] = useState<any[]>([]);
  const [questsLoading, setQuestsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setQuestsLoading(true);
      try {
        const [overviewRes, planRes, questsRes] = await Promise.all([
          api<any>("/api/student/overview"),
          api<any>("/api/student/plan"),
          api<any>("/api/quests"),
        ]);
        setOverview(overviewRes);
        setPlan(planRes?.actions || []);
        setQuests(questsRes?.quests || []);
      } catch (err: any) {
        showToast(err?.message || "Failed to load dashboard data", "error");
      } finally {
        setLoading(false);
        setQuestsLoading(false);
      }
    };
    load();
  }, [showToast]);

  const mastery = overview?.mastery || {};
  const confidence = overview?.confidence || {};
  const streak = overview?.gamification?.streak || overview?.streak || {};
  const gamification = overview?.gamification || {};
  const xpTotal = gamification?.xp_total || 0;
  const level = gamification?.level || 1;
  const nextBadge = gamification?.next_badge;
  const achievements = gamification?.achievements || [];
  const xpProgress = xpTotal % 100;
  const xpToNext = xpProgress === 0 ? 100 : 100 - xpProgress;
  const continueItem = overview?.continue || null;
  const progress = overview?.progress || [];

  const progressMax = useMemo(() => {
    const values = progress.map((p: any) => p.mastery || 0);
    return Math.max(60, ...values);
  }, [progress]);

  const formatDate = (value?: string) => {
    if (!value) return "—";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
  };

  const handlePlanAction = (action: any) => {
    const cta = String(action?.cta || "");
    if (cta.startsWith("resume_assignment:")) {
      const id = cta.split(":")[1];
      if (id) onStartTest(id);
      return;
    }
    if (cta.startsWith("resume_practice:")) {
      const id = cta.split(":")[1];
      if (id && onStartPractice) onStartPractice(id);
      return;
    }
    if (cta.startsWith("practice_concept:")) {
      const concept = cta.split(":").slice(1).join(":");
      if (concept) {
        localStorage.setItem("icodex.practice.prefill", JSON.stringify({ topic: concept }));
      }
      onNavigate("practice");
      return;
    }
    if (cta === "start_practice") {
      onNavigate("practice");
      return;
    }
    onNavigate("assigned");
  };

  const handleQuestAction = (quest: any) => {
    if (quest?.criteria?.concept) {
      localStorage.setItem(
        "icodex.practice.prefill",
        JSON.stringify({ topic: quest.criteria.concept })
      );
    }
    onNavigate("practice");
  };

  return (
    <div>
      <Hero
        title="Your Learning Companion"
        description="See mastery, focus areas, and next steps personalized by the AI tutor."
        primaryAction={{
          label: "View Assigned Tests",
          icon: Target,
          onClick: () => onNavigate("assigned"),
        }}
        secondaryAction={{
          label: "Start Practice",
          icon: BookOpen,
          onClick: () => onNavigate("practice"),
        }}
      />

      <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr] mb-8">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xl">Today's Plan</h3>
              <p className="text-sm text-[#9CA3AF]">1–3 next actions based on your mastery.</p>
            </div>
            <Chip variant="info" size="sm">
              AI Coach
            </Chip>
          </div>
          {loading ? (
            <div className="space-y-3 animate-pulse">
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
            </div>
          ) : plan.length === 0 ? (
            <div className="text-sm text-[#9CA3AF]">
              Start a practice quiz to get personalized recommendations.
            </div>
          ) : (
            <div className="space-y-3">
              {plan.map((action, idx) => (
                <div key={action.id || idx} className="glass rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold">{action.label}</p>
                    <p className="text-xs text-[#9CA3AF]">{action.reason}</p>
                  </div>
                  <Button variant="primary" size="sm" onClick={() => handlePlanAction(action)}>
                    Start
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xl">Quests & Missions</h3>
              <p className="text-sm text-[#9CA3AF]">Earn XP while shoring up weak concepts.</p>
            </div>
            <Chip variant="info" size="sm">
              Gamified
            </Chip>
          </div>
          {questsLoading ? (
            <div className="space-y-3 animate-pulse">
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
            </div>
          ) : quests.length === 0 ? (
            <div className="text-sm text-[#9CA3AF]">
              No active quests yet. Complete a practice session to unlock guided missions.
            </div>
          ) : (
            <div className="space-y-3">
              {quests.map((quest) => (
                <div key={quest.id} className="glass rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold">{quest.title}</p>
                      <p className="text-xs text-[#9CA3AF]">{quest.description}</p>
                    </div>
                    <Chip variant="success" size="xs">
                      +{quest.reward_xp} XP
                    </Chip>
                  </div>
                  <div className="space-y-1">
                    <ProgressBar progress={Math.min(100, quest.progress_percent || 0)} showLabel={false} />
                    <div className="flex justify-between text-[11px] text-[#9CA3AF]">
                      <span>{quest.progress_percent ?? 0}% complete</span>
                      <span>{quest.target} targets</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] text-[#475569]">{quest.auto ? "AI mission" : "Class quest"}</p>
                    <Button variant="secondary" size="sm" onClick={() => handleQuestAction(quest)}>
                      Continue
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-6 mb-8">
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl">Mastery Overview</h3>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-xs text-[#4169E1] underline">What is mastery?</button>
              </TooltipTrigger>
              <TooltipContent>Mastery combines accuracy, confidence, and pacing.</TooltipContent>
            </Tooltip>
          </div>
          {loading ? (
            <div className="space-y-4 animate-pulse">
              <div className="h-12 rounded-xl bg-[#E3EBFF]/60" />
              <div className="h-24 rounded-xl bg-[#E3EBFF]/60" />
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-xs text-[#9CA3AF]">Overall mastery</p>
                  <p className="text-3xl" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {mastery?.overall != null ? `${mastery.overall}%` : "—"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-[#9CA3AF]">AI confidence</p>
                  <p className="text-sm font-semibold">{confidence?.label || "Unknown"}</p>
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-[#9CA3AF] mb-2">Strong concepts</p>
                  <div className="flex flex-wrap gap-2">
                    {(mastery?.strong || []).length === 0 && (
                      <span className="text-xs text-[#9CA3AF]">Not enough data yet</span>
                    )}
                    {(mastery?.strong || []).map((c: any) => (
                      <Chip key={c.concept} variant="success" size="sm">
                        {c.concept}
                      </Chip>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-[#9CA3AF] mb-2">Needs focus</p>
                  <div className="flex flex-wrap gap-2">
                    {(mastery?.weak || []).length === 0 && (
                      <span className="text-xs text-[#9CA3AF]">No weak concepts yet</span>
                    )}
                    {(mastery?.weak || []).map((c: any) => (
                      <Chip key={c.concept} variant="warning" size="sm">
                        {c.concept}
                      </Chip>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </Card>
        <div className="grid gap-6 lg:grid-cols-3">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl">Continue where you left off</h3>
              <Sparkles className="text-[#4169E1]" size={18} />
            </div>
            {loading ? (
              <div className="h-24 rounded-xl bg-[#E3EBFF]/60 animate-pulse" />
            ) : continueItem ? (
              <div className="glass rounded-xl p-4">
                <p className="text-sm font-semibold">{continueItem.title}</p>
                <p className="text-xs text-[#9CA3AF] mb-3">
                  {continueItem.type === "assignment" ? "Assigned test" : "Practice quiz"} ·{" "}
                  {continueItem.progress}% complete
                </p>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    if (continueItem.type === "assignment") onStartTest(continueItem.assignment_id);
                    else if (onStartPractice) onStartPractice(continueItem.test_id);
                  }}
                >
                  Resume
                </Button>
              </div>
            ) : (
              <div className="text-sm text-[#9CA3AF]">
                Nothing in progress. Start a practice quiz to build momentum.
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl">Consistency</h3>
              <Flame className="text-[#F97316]" size={18} />
            </div>
            {loading ? (
              <div className="h-24 rounded-xl bg-[#E3EBFF]/60 animate-pulse" />
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-[#9CA3AF]">Current streak</p>
                    <p className="text-3xl" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                      {streak?.days ?? 0} days
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-[#9CA3AF]">Last active</p>
                    <p className="text-sm">{formatDate(streak?.last_active_at)}</p>
                  </div>
                </div>
                <Button variant="secondary" size="sm" onClick={() => onNavigate("practice")}>
                  Keep streak alive
                </Button>
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl">Progress (7 days)</h3>
              <Brain className="text-[#4169E1]" size={18} />
            </div>
            {loading ? (
              <div className="h-24 rounded-xl bg-[#E3EBFF]/60 animate-pulse" />
            ) : progress.length === 0 ? (
              <div className="text-sm text-[#9CA3AF]">No recent activity yet.</div>
            ) : (
              <div className="flex items-end gap-2 h-24">
                {progress.map((day: any) => {
                  const height = day.mastery != null ? Math.max(12, (day.mastery / progressMax) * 96) : 12;
                  return (
                    <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
                      <div
                        className="w-full rounded-lg bg-gradient-to-t from-[#4169E1] to-[#7C3AED]"
                        style={{ height }}
                      />
                      <span className="text-[10px] text-[#9CA3AF]">{day.date.slice(5)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3 mb-8">
        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xl">Level {level}</h3>
            <Chip variant="info" size="sm">
              XP Journey
            </Chip>
          </div>
          <p className="text-sm text-[#475569] mb-4">Total XP: {xpTotal}</p>
          <ProgressBar progress={Math.min(100, xpProgress)} showLabel={false} />
          <p className="text-xs text-[#9CA3AF] mt-3">
            {xpToNext} XP to level {level + 1}
          </p>
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xl">Next Badge</h3>
            <Chip variant="secondary" size="sm">
              Badges
            </Chip>
          </div>
          {nextBadge ? (
            <>
              <p className="text-sm font-semibold">{nextBadge["name"]}</p>
              <p className="text-xs text-[#9CA3AF]">{nextBadge["description"]}</p>
              <p className="text-xs text-[#22C55E] mt-3">Earn it soon to level up!</p>
            </>
          ) : (
            <p className="text-sm text-[#9CA3AF]">All badges unlocked!</p>
          )}
          <div className="mt-4 space-y-2">
            {achievements.slice(0, 3).length === 0 && (
              <p className="text-xs text-[#9CA3AF]">Unlock your first badge to get a boost.</p>
            )}
            {achievements.slice(0, 3).map((ach) => (
              <div key={ach.achievement_id} className="flex items-center justify-between text-xs">
                <span>{ach.name}</span>
                <span className="text-[#9CA3AF]">{new Date(ach.unlocked_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xl">Streak</h3>
            <Chip variant="warning" size="sm">
              {streak?.current_streak || 0} days
            </Chip>
          </div>
          <p className="text-sm text-[#475569] mb-1">
            Longest streak: {streak?.longest_streak || 0} days
          </p>
          <p className="text-xs text-[#9CA3AF]">Freeze tokens: {streak?.freeze_tokens ?? 0}</p>
          <Button variant="secondary" size="sm" onClick={() => onNavigate("practice")}>
            Keep streak alive
          </Button>
        </Card>
      </div>
    </div>
  );
}
