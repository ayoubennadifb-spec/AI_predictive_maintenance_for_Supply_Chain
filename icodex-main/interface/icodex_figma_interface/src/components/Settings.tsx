import { useEffect, useState } from "react";
import { Hero } from "./Hero";
import { Card } from "./Card";
import { Input, Select } from "./Input";
import { Button } from "./Button";
import { useToast } from "./Toast";
import { api } from "../utils/api";

interface SettingsForm {
  fullName: string;
  email: string;
  school: string;
  country: string;
  password: string;
  confirmPassword: string;
}

const DEFAULT_GAMIFICATION_CONFIG = {
  enabled: true,
  xp_base: 10,
  daily_question_cap: 60,
  improvement_bonus_multiplier: 2,
  difficulty_multipliers: { easy: 0.8, medium: 1, hard: 1.3 },
  leaderboards_enabled: true,
  quests_enabled: true,
  auto_generate_quests: true,
};

export function Settings() {
  const [form, setForm] = useState<SettingsForm>({
    fullName: "",
    email: "",
    school: "",
    country: "",
    password: "",
    confirmPassword: "",
  });
  const [learningPrefs, setLearningPrefs] = useState({
    dailyGoalMinutes: "15",
    preferredDifficulty: "medium",
    focusTopics: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [role, setRole] = useState<string>("");
  const [teacherCanAssign, setTeacherCanAssign] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});
  const [adminPermissions, setAdminPermissions] = useState<Record<string, boolean>>({});
  const [modelMeta, setModelMeta] = useState<any>({});
  const [environmentMeta, setEnvironmentMeta] = useState<any>({});
  const [systemMeta, setSystemMeta] = useState<any>(null);
  const [flagsSaving, setFlagsSaving] = useState(false);
  const [permissionsSaving, setPermissionsSaving] = useState(false);
  const [gamificationConfig, setGamificationConfig] = useState<any>(DEFAULT_GAMIFICATION_CONFIG);
  const [gamificationSaving, setGamificationSaving] = useState(false);
  const { showToast } = useToast();

  const difficultyOptions = [
    { value: "easy", label: "Mostly Easy" },
    { value: "medium", label: "Balanced" },
    { value: "hard", label: "Challenge" },
    { value: "mixed", label: "Mixed" },
  ];

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const data = await api<{ user: any }>("/api/auth/me");
        const user = data.user || {};
        setRole(user.role || "");
        setForm((prev) => ({
          ...prev,
          fullName: user.fullName || user.full_name || "",
          email: user.email || "",
          school: user.school || "",
          country: user.country || "",
        }));
        const prefs = user.learning_preferences || user.learningPreferences || {};
        setLearningPrefs({
          dailyGoalMinutes: String(prefs.daily_goal_minutes ?? 15),
          preferredDifficulty: prefs.preferred_difficulty || "medium",
          focusTopics: Array.isArray(prefs.focus_topics)
            ? prefs.focus_topics.join(", ")
            : prefs.focus_topics || "",
        });

            if ((user.role || "") === "admin") {
              setConfigLoading(true);
              try {
                const cfg = await api<{ config: any }>("/api/config");
                setTeacherCanAssign(!!cfg?.config?.teacher_can_assign);
                setFeatureFlags(cfg?.config?.feature_flags || {});
                setAdminPermissions(cfg?.config?.admin_permissions || {});
                setModelMeta(cfg?.config?.model_meta || {});
                setEnvironmentMeta(cfg?.config?.environment || {});
                setGamificationConfig(cfg?.config?.gamification || DEFAULT_GAMIFICATION_CONFIG);
                const meta = await api<any>("/api/system/meta").catch(() => null);
            if (meta) {
              setSystemMeta(meta);
              if (!cfg?.config?.environment) {
                setEnvironmentMeta(meta.environment || {});
              }
              if (!cfg?.config?.model_meta) {
                setModelMeta(meta.model_meta || {});
              }
            }
          } catch (err: any) {
            showToast(err?.message || "Failed to load admin settings", "error");
          } finally {
            setConfigLoading(false);
          }
        }
      } catch (err: any) {
        showToast(err?.message || "Failed to load profile", "error");
      } finally {
        setLoading(false);
      }
    };
    loadProfile();
  }, [showToast]);

  const handleChange =
    (field: keyof SettingsForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
    };

  const formatMetaDate = (value?: string) => {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
  };

  const handleSave = async () => {
    if (form.password && form.password !== form.confirmPassword) {
      showToast("Passwords do not match", "error");
      return;
    }
    try {
      setSaving(true);
      const payload: any = {
        fullName: form.fullName,
        school: form.school,
        country: form.country,
      };
      if (learningPrefs.dailyGoalMinutes) {
        payload.daily_goal_minutes = learningPrefs.dailyGoalMinutes;
      }
      if (learningPrefs.preferredDifficulty) {
        payload.preferred_difficulty = learningPrefs.preferredDifficulty;
      }
      payload.focus_topics = learningPrefs.focusTopics;
      if (form.password) {
        payload.password = form.password;
      }
      await api("/api/auth/me", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Settings updated", "success");
      setForm((prev) => ({ ...prev, password: "", confirmPassword: "" }));
    } catch (err: any) {
      showToast(err?.message || "Failed to update settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateFeatureFlag = async (key: string, value: boolean) => {
    const next = { ...featureFlags, [key]: value };
    setFeatureFlags(next);
    setFlagsSaving(true);
    try {
      await api("/api/config", {
        method: "PUT",
        body: JSON.stringify({ feature_flags: next }),
      });
      showToast("Feature flags updated", "success");
    } catch (err: any) {
      showToast(err?.message || "Failed to update feature flags", "error");
    } finally {
      setFlagsSaving(false);
    }
  };

  const updatePermission = async (key: string, value: boolean) => {
    const next = { ...adminPermissions, [key]: value };
    setAdminPermissions(next);
    setPermissionsSaving(true);
    try {
      await api("/api/config", {
        method: "PUT",
        body: JSON.stringify({ admin_permissions: next }),
      });
      showToast("Permissions updated", "success");
    } catch (err: any) {
      showToast(err?.message || "Failed to update permissions", "error");
    } finally {
      setPermissionsSaving(false);
    }
  };

  const saveGamificationConfig = async (nextConfig: any) => {
    setGamificationConfig(nextConfig);
    setGamificationSaving(true);
    try {
      await api("/api/config", {
        method: "PUT",
        body: JSON.stringify({ gamification: nextConfig }),
      });
      showToast("Gamification settings updated", "success");
    } catch (err: any) {
      showToast(err?.message || "Failed to update gamification", "error");
    } finally {
      setGamificationSaving(false);
    }
  };

  const toggleGamificationFlag = (flag: "leaderboards_enabled" | "quests_enabled" | "auto_generate_quests") => {
    const next = {
      ...gamificationConfig,
      [flag]: !(gamificationConfig as any)[flag],
    };
    saveGamificationConfig(next);
  };

  return (
    <div>
      <Hero
        title="Settings"
        description="Manage your profile information and account preferences"
      />

      <div className="grid gap-6 md:grid-cols-[2fr,1fr] mt-4">
        <Card>
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Profile</h2>
            {loading ? (
              <p className="text-sm text-[#9CA3AF]">Loading profile...</p>
            ) : (
              <>
                <Input
                  label="Full Name"
                  placeholder="Your name"
                  value={form.fullName}
                  onChange={handleChange("fullName")}
                />
                <Input
                  label="Email"
                  type="email"
                  disabled
                  value={form.email}
                  onChange={handleChange("email")}
                  helperText="Email is managed by the administrator."
                />
                <div className="grid md:grid-cols-2 gap-4">
                  <Input
                    label="School / Institution"
                    placeholder="Your school or institution"
                    value={form.school}
                    onChange={handleChange("school")}
                  />
                  <Input
                    label="Country"
                    placeholder="Your country"
                    value={form.country}
                    onChange={handleChange("country")}
                  />
                </div>
              </>
            )}
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Password</h2>
            <p className="text-xs text-[#9CA3AF]">
              Leave the fields below empty if you don&apos;t want to change your
              password.
            </p>
            <Input
              label="New Password"
              type="password"
              placeholder="••••••••"
              value={form.password}
              onChange={handleChange("password")}
            />
            <Input
              label="Confirm New Password"
              type="password"
              placeholder="••••••••"
              value={form.confirmPassword}
              onChange={handleChange("confirmPassword")}
            />
          </div>
        </Card>
      </div>

      {role === "student" && (
        <div className="mt-6">
          <Card>
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold">Learning Preferences</h2>
                <p className="text-sm text-[#9CA3AF]">
                  Personalize your daily plan, difficulty, and focus concepts.
                </p>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <Input
                  label="Daily Goal (minutes)"
                  type="number"
                  min={5}
                  max={180}
                  value={learningPrefs.dailyGoalMinutes}
                  onChange={(e) =>
                    setLearningPrefs((prev) => ({ ...prev, dailyGoalMinutes: e.target.value }))
                  }
                  helperText="Used to build your daily plan."
                />
                <Select
                  label="Preferred Difficulty"
                  options={difficultyOptions}
                  value={learningPrefs.preferredDifficulty}
                  onChange={(e) =>
                    setLearningPrefs((prev) => ({ ...prev, preferredDifficulty: e.target.value }))
                  }
                />
              </div>
              <Input
                label="Focus Topics"
                placeholder="e.g., Loops, Functions"
                value={learningPrefs.focusTopics}
                onChange={(e) => setLearningPrefs((prev) => ({ ...prev, focusTopics: e.target.value }))}
                helperText="Comma-separated topics to prioritize in practice."
              />
            </div>
          </Card>
        </div>
      )}

      <div className="mt-6 flex justify-end">
        <Button variant="primary" onClick={handleSave} disabled={saving || loading}>
          {saving ? "Saving..." : "Save Changes"}
        </Button>
      </div>

      {role === "admin" && (
        <>
          <div className="grid gap-6 md:grid-cols-2 mt-6">
            <Card>
              <h2 className="text-lg font-semibold mb-2">AI Model</h2>
              <p className="text-sm text-[#9CA3AF] mb-4">
                Active evaluation model and last update time.
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Provider</span>
                  <span>{modelMeta?.provider || systemMeta?.model_meta?.provider || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Model</span>
                  <span>{modelMeta?.active_model || systemMeta?.model_meta?.active_model || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Last Updated</span>
                  <span>{formatMetaDate(modelMeta?.last_updated_at || systemMeta?.model_meta?.last_updated_at)}</span>
                </div>
              </div>
            </Card>

            <Card>
              <h2 className="text-lg font-semibold mb-2">Environment</h2>
              <p className="text-sm text-[#9CA3AF] mb-4">
                Runtime and database health indicators.
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Environment</span>
                  <span>{environmentMeta?.name || systemMeta?.environment?.name || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Version</span>
                  <span>{environmentMeta?.version || systemMeta?.environment?.version || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#9CA3AF]">Database</span>
                  <span className={systemMeta?.db?.db_ok ? "text-[#22C55E]" : "text-[#EF4444]"}>
                    {systemMeta?.db?.db_ok ? "Connected" : "Unavailable"}
                  </span>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid gap-6 md:grid-cols-2 mt-6">
            <Card>
              <h2 className="text-lg font-semibold mb-2">Feature Flags</h2>
              <p className="text-sm text-[#9CA3AF] mb-4">Control AI-driven product features.</p>
              <div className="space-y-3">
                {Object.keys(featureFlags).length === 0 && (
                  <p className="text-sm text-[#9CA3AF]">No feature flags configured.</p>
                )}
                {Object.entries(featureFlags).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-sm">{key.replace(/_/g, " ")}</span>
                    <Button
                      variant={value ? "secondary" : "primary"}
                      size="sm"
                      disabled={flagsSaving}
                      onClick={() => updateFeatureFlag(key, !value)}
                    >
                      {value ? "On" : "Off"}
                    </Button>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <h2 className="text-lg font-semibold mb-2">Admin Permissions</h2>
              <p className="text-sm text-[#9CA3AF] mb-4">Granular controls for admin scope.</p>
              <div className="space-y-3">
                {Object.keys(adminPermissions).length === 0 && (
                  <p className="text-sm text-[#9CA3AF]">No permissions configured.</p>
                )}
                {Object.entries(adminPermissions).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-sm">{key.replace(/_/g, " ")}</span>
                    <Button
                      variant={value ? "secondary" : "primary"}
                      size="sm"
                      disabled={permissionsSaving}
                      onClick={() => updatePermission(key, !value)}
                    >
                      {value ? "Enabled" : "Disabled"}
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="grid gap-6 md:grid-cols-2 mt-6">
            <Card>
              <h2 className="text-lg font-semibold mb-2">Gamification</h2>
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm text-[#475569]">Enable gamified XP, events, and streaks.</p>
                <Button
                  variant={gamificationConfig.enabled ? "secondary" : "primary"}
                  size="sm"
                  disabled={gamificationSaving}
                  onClick={() =>
                    saveGamificationConfig({ ...gamificationConfig, enabled: !gamificationConfig.enabled })
                  }
                >
                  {gamificationConfig.enabled ? "Disable" : "Enable"}
                </Button>
              </div>
              <div className="grid md:grid-cols-3 gap-3">
                <Input
                  label="XP Base"
                  type="number"
                  value={gamificationConfig.xp_base}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({ ...prev, xp_base: Number(e.target.value) }))
                  }
                />
                <Input
                  label="Daily question cap"
                  type="number"
                  value={gamificationConfig.daily_question_cap}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({
                      ...prev,
                      daily_question_cap: Number(e.target.value),
                    }))
                  }
                />
                <Input
                  label="Improvement multiplier"
                  type="number"
                  value={gamificationConfig.improvement_bonus_multiplier}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({
                      ...prev,
                      improvement_bonus_multiplier: Number(e.target.value),
                    }))
                  }
                />
              </div>
              <div className="grid md:grid-cols-3 gap-3 mt-3">
                <Input
                  label="Easy multiplier"
                  type="number"
                  value={gamificationConfig.difficulty_multipliers?.easy}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({
                      ...prev,
                      difficulty_multipliers: {
                        ...(prev.difficulty_multipliers || {}),
                        easy: Number(e.target.value),
                      },
                    }))
                  }
                />
                <Input
                  label="Medium multiplier"
                  type="number"
                  value={gamificationConfig.difficulty_multipliers?.medium}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({
                      ...prev,
                      difficulty_multipliers: {
                        ...(prev.difficulty_multipliers || {}),
                        medium: Number(e.target.value),
                      },
                    }))
                  }
                />
                <Input
                  label="Hard multiplier"
                  type="number"
                  value={gamificationConfig.difficulty_multipliers?.hard}
                  onChange={(e) =>
                    setGamificationConfig((prev: any) => ({
                      ...prev,
                      difficulty_multipliers: {
                        ...(prev.difficulty_multipliers || {}),
                        hard: Number(e.target.value),
                      },
                    }))
                  }
                />
              </div>
              <div className="flex flex-wrap gap-3 mt-4">
                <Button
                  variant={gamificationConfig.leaderboards_enabled ? "secondary" : "primary"}
                  size="sm"
                  onClick={() => toggleGamificationFlag("leaderboards_enabled")}
                  disabled={gamificationSaving}
                >
                  {gamificationConfig.leaderboards_enabled ? "Leaderboards on" : "Leaderboards off"}
                </Button>
                <Button
                  variant={gamificationConfig.quests_enabled ? "secondary" : "primary"}
                  size="sm"
                  onClick={() => toggleGamificationFlag("quests_enabled")}
                  disabled={gamificationSaving}
                >
                  {gamificationConfig.quests_enabled ? "Quests enabled" : "Quests disabled"}
                </Button>
                <Button
                  variant={gamificationConfig.auto_generate_quests ? "secondary" : "primary"}
                  size="sm"
                  onClick={() => toggleGamificationFlag("auto_generate_quests")}
                  disabled={gamificationSaving}
                >
                  {gamificationConfig.auto_generate_quests ? "Auto quests on" : "Auto quests off"}
                </Button>
              </div>
              <div className="mt-4 flex justify-end">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => saveGamificationConfig(gamificationConfig)}
                  disabled={gamificationSaving}
                >
                  {gamificationSaving ? "Saving..." : "Save"}
                </Button>
              </div>
            </Card>
          </div>

          <div className="mt-6">
            <Card>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold">Teacher Assignment Rules</h2>
                  <p className="text-sm text-[#9CA3AF] mt-1">
                    Allow teachers to assign tests directly to classes they teach.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`
                      px-3 py-1 rounded-full text-sm font-medium
                      ${teacherCanAssign ? "bg-[#22C55E]/10 text-[#22C55E]" : "bg-[#F97316]/10 text-[#F97316]"}
                    `}
                  >
                    {teacherCanAssign ? "ON" : "OFF"}
                  </span>
                  <Button
                    variant={teacherCanAssign ? "secondary" : "primary"}
                    size="sm"
                    disabled={configLoading}
                    onClick={async () => {
                      try {
                        const next = !teacherCanAssign;
                        setTeacherCanAssign(next);
                        await api("/api/config", {
                          method: "PUT",
                          body: JSON.stringify({ teacher_can_assign: next }),
                        });
                        showToast(
                          next ? "Teacher direct assignment enabled" : "Teacher direct assignment disabled",
                          "success"
                        );
                      } catch (err: any) {
                        showToast(err?.message || "Failed to update admin settings", "error");
                      }
                    }}
                  >
                    {teacherCanAssign ? "Disable" : "Enable"}
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
