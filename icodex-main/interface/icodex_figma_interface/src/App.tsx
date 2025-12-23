import { useEffect, useState } from "react";
import { Landing } from "./components/Landing";
import { Auth } from "./components/Auth";
import { Shell } from "./components/Shell";
import { ToastProvider, useToast } from "./components/Toast";
import { QuizTaking } from "./components/QuizTaking";
import { api } from "./utils/api";

// Admin Components
import { AdminDashboard } from "./components/admin/AdminDashboard";
import { AdminUsers } from "./components/admin/AdminUsers";
import { AdminClasses } from "./components/admin/AdminClasses";
import { AdminTests } from "./components/admin/AdminTests";

// Teacher Components
import { TeacherDashboard } from "./components/teacher/TeacherDashboard";
import { QuizStudio } from "./components/teacher/QuizStudio";
import { TeacherTests } from "./components/teacher/TeacherTests";

// Student Components
import { StudentDashboard } from "./components/student/StudentDashboard";
import { AssignedTests } from "./components/student/AssignedTests";
import { Practice } from "./components/student/Practice";

// Shared Components
import { Reports } from "./components/Reports";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Settings } from "./components/Settings";

type Screen = "landing" | "login" | "signup" | "app" | "quiz";
type Role = "admin" | "teacher" | "student";

function AppContent() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [role, setRole] = useState<Role>("student");
  const [userName, setUserName] = useState("John Doe");
  const [activeNav, setActiveNav] = useState("dashboard");
  const [activeTestId, setActiveTestId] = useState<string | null>(null);
  const [activeAssignmentId, setActiveAssignmentId] = useState<string | null>(null);
  const [quizMode, setQuizMode] = useState<"practice" | "assigned">("practice");
  const { showToast } = useToast();
  const [loading, setLoading] = useState(true);

  const hydrateSession = async () => {
    try {
      const data = await api<{ user: any }>('/api/auth/me');
      if (data?.user) {
        const detectedRole = (data.user.role as Role) || 'student';
        setRole(detectedRole);
        setUserName(data.user.fullName || data.user.full_name || data.user.email || 'User');
        setScreen("app");
        setActiveNav("dashboard");
        window.history.replaceState(null, "", "/dashboard");
      } else {
        setScreen("landing");
      }
    } catch {
      setScreen("landing");
    } finally {
      setLoading(false);
    }
  };

  // On mount, try to fetch current session
  useEffect(() => {
    hydrateSession();
  }, []);

  const handleAuth = async (data: any) => {
    try {
      if (authMode === "signup") {
        const payload = {
          fullName: data.name,
          email: data.email,
          password: data.password,
          role: data.role || "student",
          school: data.school,
          country: data.country,
        };
        await api('/api/auth/signup', { method: 'POST', body: JSON.stringify(payload) });
      } else {
        await api('/api/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email: data.email, password: data.password }),
        });
      }
      await hydrateSession();
      setScreen("app");
      setActiveNav("dashboard");
      window.history.replaceState(null, "", "/dashboard");
      showToast(`Welcome ${data.name || "back"}!`, "success");
    } catch (err: any) {
      showToast(err?.message || "Authentication failed", "error");
    }
  };

  const handleLogout = async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } catch {}
    setScreen("landing");
    setActiveNav("dashboard");
    showToast("Logged out successfully", "info");
  };

  const handleStartAssigned = (assignmentId: string) => {
    setActiveAssignmentId(assignmentId);
    setQuizMode("assigned");
    setActiveTestId(null);
    setScreen("quiz");
  };

  const handleStartPractice = (testId: string) => {
    setActiveTestId(testId);
    setActiveAssignmentId(null);
    setQuizMode("practice");
    setScreen("quiz");
  };

  const handleExitQuiz = () => {
    setActiveTestId(null);
    setActiveAssignmentId(null);
    setScreen("app");
    setActiveNav("dashboard");
  };

  const handleNavClick = (nav: string) => {
    setActiveNav(nav);
  };

  // Landing page
  if (loading) {
    return null;
  }

  if (screen === "landing") {
    return (
      <Landing
        onLogin={() => {
          setAuthMode("login");
          setScreen("login");
        }}
        onSignup={() => {
          setAuthMode("signup");
          setScreen("signup");
        }}
      />
    );
  }

  // Auth screens
  if (screen === "login" || screen === "signup") {
    return (
      <Auth
        mode={authMode}
        onSubmit={handleAuth}
        onToggleMode={() => {
          const newMode = authMode === "login" ? "signup" : "login";
          setAuthMode(newMode);
          setScreen(newMode);
        }}
        onBack={() => setScreen("landing")}
      />
    );
  }

  // Quiz taking
  if (screen === "quiz" && (activeTestId || activeAssignmentId)) {
    return (
      <QuizTaking
        mode={quizMode}
        testId={activeTestId || undefined}
        assignmentId={activeAssignmentId || undefined}
        onExit={handleExitQuiz}
      />
    );
  }

  // Main app with shell
  return (
    <Shell
      role={role}
      userName={userName}
      activeNav={activeNav}
      onNavClick={handleNavClick}
      onLogout={handleLogout}
    >
      {/* Admin Pages */}
      {role === "admin" && (
        <>
          {activeNav === "dashboard" && <AdminDashboard />}
          {activeNav === "users" && <AdminUsers />}
          {activeNav === "classes" && <AdminClasses />}
          {activeNav === "tests" && <AdminTests />}
          {activeNav === "reports" && <Reports />}
          {activeNav === "settings" && <Settings />}
        </>
      )}

      {/* Teacher Pages */}
      {role === "teacher" && (
        <>
          {activeNav === "dashboard" && <TeacherDashboard onNavigate={setActiveNav} />}
          {activeNav === "studio" && <QuizStudio />}
          {activeNav === "tests" && <TeacherTests />}
          {activeNav === "reports" && <Reports />}
          {activeNav === "settings" && <Settings />}
        </>
      )}

      {/* Student Pages */}
      {role === "student" && (
        <>
          {activeNav === "dashboard" && (
            <StudentDashboard onNavigate={setActiveNav} onStartTest={handleStartAssigned} onStartPractice={handleStartPractice} />
          )}
          {activeNav === "assigned" && (
            <AssignedTests
              onStartTest={handleStartAssigned}
              onViewReports={() => setActiveNav("reports")}
            />
          )}
          {activeNav === "practice" && <Practice onStartPractice={handleStartPractice} />}
          {activeNav === "reports" && <Reports />}
          {activeNav === "settings" && <Settings />}
        </>
      )}
    </Shell>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </ErrorBoundary>
  );
}
