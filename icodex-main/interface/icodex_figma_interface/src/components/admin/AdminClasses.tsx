import { useEffect, useState } from "react";
import { Plus, Users, GraduationCap } from "lucide-react";
import { Hero } from "../Hero";
import { Table } from "../Table";
import { Button } from "../Button";
import { Modal } from "../Modal";
import { Input } from "../Input";
import { Chip } from "../Chip";
import { useToast } from "../Toast";
import { api } from "../../utils/api";

export function AdminClasses() {
  const [showAddModal, setShowAddModal] = useState(false);
  const { showToast } = useToast();

  const [classes, setClasses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<any[]>([]);
  const [manageClass, setManageClass] = useState<any | null>(null);
  const [classHealth, setClassHealth] = useState<Record<string, any>>({});
  const [classAnalytics, setClassAnalytics] = useState<any | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [selectedTeacher, setSelectedTeacher] = useState("");
  const [selectedStudent, setSelectedStudent] = useState("");
  const [visibleTeachers, setVisibleTeachers] = useState<any[]>([]);
  const [visibleStudents, setVisibleStudents] = useState<any[]>([]);

  const [newClass, setNewClass] = useState({
    name: "",
    description: "",
  });

  const fetchClasses = async () => {
    try {
      const data = await api<{ classes: any[] }>('/api/classes');
      const normalized = (data.classes || []).map((c: any) => ({
        id: c.id,
        name: c.name,
        teacherCount: c.teacherIds?.length || c.teachers?.length || 0,
        studentCount: c.studentIds?.length || c.students?.length || 0,
        createdAt: c.createdAt || c.created_at || new Date().toISOString(),
        description: c.description || "",
        teachers: c.teachers || [],
        students: c.students || [],
      }));
      setClasses(normalized);
    } catch (err: any) {
      showToast(err?.message || "Failed to load classes", "error");
    } finally {
      setLoading(false);
    }
  };

  const fetchClassHealth = async () => {
    try {
      const data = await api<{ classes: Record<string, any> }>("/api/classes/health");
      setClassHealth(data.classes || {});
    } catch {
      setClassHealth({});
    }
  };

  useEffect(() => {
    fetchClasses();
    fetchClassHealth();
    api<{ users: any[] }>('/api/users')
      .then((res) => setUsers(res.users || []))
      .catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    if (!manageClass) {
      setClassAnalytics(null);
      return;
    }
    setAnalyticsLoading(true);
    api(`/api/classes/${manageClass.id}/analytics`)
      .then((res) => setClassAnalytics(res))
      .catch(() => setClassAnalytics(null))
      .finally(() => setAnalyticsLoading(false));
  }, [manageClass]);

  const handleAddClass = () => {
    if (!newClass.name) {
      showToast("Please enter a class name", "error");
      return;
    }

    api('/api/classes', {
      method: 'POST',
      body: JSON.stringify({ name: newClass.name, description: newClass.description }),
    })
      .then(() => {
        showToast("Class created successfully", "success");
        setShowAddModal(false);
        setNewClass({ name: "", description: "" });
        fetchClasses();
        fetchClassHealth();
      })
      .catch((err) => showToast(err?.message || "Failed to create class", "error"));
    
  };

  const columns = [
    { key: "name", label: "Class Name" },
    {
      key: "teacherCount",
      label: "Teachers",
      render: (cls: any) => (
        <div className="flex items-center gap-2">
          <GraduationCap size={16} className="text-[#7C3AED]" />
          <span>{cls.teacherCount}</span>
        </div>
      ),
    },
    {
      key: "studentCount",
      label: "Students",
      render: (cls: any) => (
        <div className="flex items-center gap-2">
          <Users size={16} className="text-[#4169E1]" />
          <span>{cls.studentCount}</span>
        </div>
      ),
    },
    {
      key: "health",
      label: "Learning Health",
      render: (cls: any) => {
        const health = classHealth[cls.id];
        if (!health || health.avg_mastery == null) {
          return <span className="text-xs text-[#9CA3AF]">No data</span>;
        }
        const avg = health.avg_mastery;
        const struggling = health.struggling_percent ?? 0;
        const variant = avg >= 75 ? "success" : avg >= 60 ? "warning" : "error";
        return (
          <div className="flex flex-col gap-1">
            <Chip variant={variant as any} size="sm">
              {avg}%
            </Chip>
            <span className="text-xs text-[#9CA3AF]">{struggling}% struggling</span>
          </div>
        );
      },
    },
    {
      key: "activity",
      label: "Recent Activity",
      render: (cls: any) => {
        const health = classHealth[cls.id];
        if (!health) return <span className="text-xs text-[#9CA3AF]">—</span>;
        return (
          <div className="text-xs text-[#475569]">
            <div>{health.recent_answers ?? 0} answers</div>
            <div className="text-[#9CA3AF]">{health.last_activity_at || "No activity"}</div>
          </div>
        );
      },
    },
    { key: "createdAt", label: "Created At" },
    {
      key: "actions",
      label: "Actions",
      render: (cls: any) => (
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => { setManageClass(cls); setSelectedTeacher(""); setSelectedStudent(""); }}>
            Manage
          </Button>
          <Button
            variant="tertiary"
            size="sm"
            onClick={async () => {
              if (!window.confirm(`Delete class "${cls.name}" permanently? This cannot be undone.`)) return;
              try {
                await api(`/api/classes/${cls.id}`, { method: "DELETE" });
                showToast("Class deleted", "success");
                if (manageClass?.id === cls.id) setManageClass(null);
                fetchClasses();
                fetchClassHealth();
              } catch (err: any) {
                showToast(err?.message || "Failed to delete class", "error");
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
        title="Class Management"
        description="Create and manage classes, assign teachers and students"
        primaryAction={{
          label: "Create Class",
          icon: Plus,
          onClick: () => setShowAddModal(true),
        }}
      />

      <Table data={classes} columns={columns} loading={loading} />

      {/* Add Class Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Create New Class"
        description="Add a new class to the platform"
        footer={
          <>
            <Button variant="tertiary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleAddClass}>
              Create Class
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Class Name *"
            value={newClass.name}
            onChange={(e) => setNewClass({ ...newClass, name: e.target.value })}
            placeholder="e.g., Computer Science 101"
          />
          <Input
            label="Description"
            value={newClass.description}
            onChange={(e) => setNewClass({ ...newClass, description: e.target.value })}
            placeholder="Brief description of the class"
          />
        </div>
      </Modal>

      {/* Manage Class Modal */}
      <Modal
        isOpen={!!manageClass}
        onClose={() => setManageClass(null)}
        title={`Manage "${manageClass?.name || ""}"`}
        description="Assign teachers and students to this class"
        footer={
          <Button variant="tertiary" onClick={() => setManageClass(null)}>
            Close
          </Button>
        }
      >
        <div className="space-y-4">
          <div className="glass rounded-xl p-4 bg-[#E3EBFF]/30">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm text-[#9CA3AF]">Class Insights</p>
                <p className="text-lg font-semibold">{manageClass?.name}</p>
              </div>
              {analyticsLoading && <span className="text-xs text-[#9CA3AF]">Loading...</span>}
            </div>
            {!analyticsLoading && classAnalytics && (
              <div className="space-y-4">
                <div className="grid md:grid-cols-3 gap-3">
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-[#9CA3AF]">Avg Mastery</p>
                    <p className="text-lg">{classAnalytics.health?.avg_mastery ?? "--"}%</p>
                  </div>
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-[#9CA3AF]">Struggling</p>
                    <p className="text-lg">{classAnalytics.health?.struggling_percent ?? "--"}%</p>
                  </div>
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-[#9CA3AF]">Recent Answers</p>
                    <p className="text-lg">{classAnalytics.activity?.recent_answers ?? 0}</p>
                  </div>
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="glass rounded-xl p-3">
                    <p className="text-sm text-[#9CA3AF] mb-2">Concept Coverage</p>
                    <div className="flex flex-wrap gap-2">
                      {(classAnalytics.concepts?.coverage || []).slice(0, 8).map((c: any) => (
                        <Chip key={c.concept} variant="info" size="sm">
                          {c.concept} · {c.questions}
                        </Chip>
                      ))}
                      {(classAnalytics.concepts?.coverage || []).length === 0 && (
                        <span className="text-xs text-[#9CA3AF]">No coverage yet</span>
                      )}
                    </div>
                  </div>
                  <div className="glass rounded-xl p-3">
                    <p className="text-sm text-[#9CA3AF] mb-2">Weak Concepts</p>
                    <div className="space-y-2">
                      {(classAnalytics.concepts?.mastery || []).slice(0, 5).map((c: any) => (
                        <div key={c.concept} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span>{c.concept}</span>
                            <span className="text-[#9CA3AF]">{c.avg_mastery}%</span>
                          </div>
                          <div className="h-2 bg-[#E5E7EB] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-[#F97316]"
                              style={{ width: `${Math.min(100, c.avg_mastery)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                      {(classAnalytics.concepts?.mastery || []).length === 0 && (
                        <span className="text-xs text-[#9CA3AF]">No mastery data yet</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
            {!analyticsLoading && !classAnalytics && (
              <p className="text-xs text-[#9CA3AF]">No analytics available yet.</p>
            )}
          </div>

          <div className="grid gap-2">
            <label className="text-sm text-[#475569]">Assign Teacher</label>
            <select
              className="glass rounded-xl px-3 py-2 outline-none"
              value={selectedTeacher}
              onChange={(e) => setSelectedTeacher(e.target.value)}
            >
              <option value="">Select a teacher</option>
              {users.filter((u) => u.role === "teacher").map((u) => (
                <option key={u.id} value={u.id}>{u.full_name || u.name || u.email}</option>
              ))}
            </select>
            <Button
              variant="primary"
              disabled={!selectedTeacher}
              onClick={() => {
                if (!manageClass || !selectedTeacher) return;
                api('/api/classes/assign-teacher', {
                  method: 'POST',
                  body: JSON.stringify({ class_id: manageClass.id, teacher_id: selectedTeacher }),
                })
                  .then(() => {
                    showToast("Teacher assigned", "success");
                    setVisibleTeachers((prev) => [...prev, selectedTeacher]);
                    fetchClasses();
                    fetchClassHealth();
                  })
                  .catch((err: any) => showToast(err?.message || "Failed to assign teacher", "error"));
              }}
            >
              Assign Teacher
            </Button>
          </div>

          <div className="grid gap-2">
            <label className="text-sm text-[#475569]">Assign Student</label>
            <select
              className="glass rounded-xl px-3 py-2 outline-none"
              value={selectedStudent}
              onChange={(e) => setSelectedStudent(e.target.value)}
            >
              <option value="">Select a student</option>
              {users.filter((u) => u.role === "student").map((u) => (
                <option key={u.id} value={u.id}>{u.full_name || u.name || u.email}</option>
              ))}
            </select>
            <Button
              variant="secondary"
              disabled={!selectedStudent}
              onClick={() => {
                if (!manageClass || !selectedStudent) return;
                api('/api/classes/assign-student', {
                  method: 'POST',
                  body: JSON.stringify({ class_id: manageClass.id, student_id: selectedStudent }),
                })
                  .then(() => {
                    showToast("Student assigned", "success");
                    setVisibleStudents((prev) => [...prev, selectedStudent]);
                    fetchClasses();
                    fetchClassHealth();
                  })
                  .catch((err: any) => showToast(err?.message || "Failed to assign student", "error"));
              }}
            >
              Assign Student
            </Button>
          </div>

          {/* Current assignments */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="glass rounded-xl p-3">
              <p className="text-sm text-[#475569] mb-2">Teachers</p>
              <div className="space-y-2">
                {(manageClass?.teachers || []).map((tid: string) => {
                  const t = users.find((u) => u.id === tid);
                  const label = t ? (t.full_name || t.name || t.email) : tid;
                  return (
                    <div key={tid} className="flex items-center justify-between text-sm">
                      <span>{label}</span>
                      <Button
                        variant="tertiary"
                        size="sm"
                        onClick={() => {
                          api('/api/classes/remove-teacher', {
                            method: 'POST',
                            body: JSON.stringify({ class_id: manageClass.id, teacher_id: tid }),
                          })
                            .then(() => { showToast("Teacher removed", "info"); fetchClasses(); fetchClassHealth(); })
                            .catch((err: any) => showToast(err?.message || "Failed to remove teacher", "error"));
                        }}
                      >
                        Remove
                      </Button>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="glass rounded-xl p-3">
              <p className="text-sm text-[#475569] mb-2">Students</p>
              <div className="space-y-2">
                {(manageClass?.students || []).map((sid: string) => {
                  const s = users.find((u) => u.id === sid);
                  const label = s ? (s.full_name || s.name || s.email) : sid;
                  return (
                    <div key={sid} className="flex items-center justify-between text-sm">
                      <span>{label}</span>
                      <Button
                        variant="tertiary"
                        size="sm"
                        onClick={() => {
                          api('/api/classes/remove-student', {
                            method: 'POST',
                            body: JSON.stringify({ class_id: manageClass.id, student_id: sid }),
                          })
                            .then(() => { showToast("Student removed", "info"); fetchClasses(); fetchClassHealth(); })
                            .catch((err: any) => showToast(err?.message || "Failed to remove student", "error"));
                        }}
                      >
                        Remove
                      </Button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
