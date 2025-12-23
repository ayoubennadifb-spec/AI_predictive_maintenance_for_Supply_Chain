import { motion } from "motion/react";
import {
  LayoutGrid,
  Users,
  GraduationCap,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  Sparkles,
  Target,
  BookOpen,
} from "lucide-react";
import { Chip } from "./Chip";

interface ShellProps {
  children: React.ReactNode;
  role: "admin" | "teacher" | "student";
  userName: string;
  activeNav: string;
  onNavClick: (nav: string) => void;
  onLogout: () => void;
}

export function Shell({ children, role, userName, activeNav, onNavClick, onLogout }: ShellProps) {
  const navItems = {
    admin: [
      { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
      { id: "users", label: "Users", icon: Users },
      { id: "classes", label: "Classes", icon: GraduationCap },
      { id: "tests", label: "Tests", icon: FileText },
      { id: "reports", label: "Reports", icon: BarChart3 },
    ],
    teacher: [
      { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
      { id: "studio", label: "Quiz Studio", icon: Sparkles },
      { id: "tests", label: "My Tests", icon: FileText },
      { id: "reports", label: "Reports", icon: BarChart3 },
    ],
    student: [
      { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
      { id: "assigned", label: "Assigned Tests", icon: Target },
      { id: "practice", label: "Practice", icon: BookOpen },
      { id: "reports", label: "Reports", icon: BarChart3 },
    ],
  };

  const roleColors = {
    admin: "#EF4444",
    teacher: "#7C3AED",
    student: "#4169E1",
  };

  const items = navItems[role];

  return (
    <div className="min-h-screen flex">
      {/* Left Rail Navigation */}
      <motion.div
        initial={{ x: -20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-64 glass border-r border-[#1E293B]/10 flex flex-col"
      >
        {/* Logo */}
        <div className="p-6 border-b border-[#1E293B]/10">
          <img
            src="/icodex_logo_full.svg"
            alt="ICODEX MODEL"
            className="h-12 w-auto max-w-full object-contain mix-blend-multiply"
          />
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 p-4 space-y-1">
          {items.map((item) => {
            const Icon = item.icon;
            const isActive = activeNav === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavClick(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                  isActive
                    ? "bg-[#4169E1] text-white shadow-lg shadow-blue-500/30"
                    : "text-[#475569] hover:bg-[#E3EBFF]"
                }`}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Bottom Actions */}
        <div className="p-4 space-y-2 border-t border-[#1E293B]/10">
          <button
            onClick={() => onNavClick("settings")}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-[#475569] hover:bg-[#E3EBFF] transition-all"
          >
            <Settings size={20} />
            <span>Settings</span>
          </button>
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-[#EF4444] hover:bg-[#EF4444]/10 transition-all"
          >
            <LogOut size={20} />
            <span>Logout</span>
          </button>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Top Bar */}
        <motion.div
          initial={{ y: -20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="glass border-b border-[#1E293B]/10 p-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <Chip variant="info" size="sm">
              ● Live
            </Chip>
            <span className="text-sm text-[#9CA3AF]">Environment</span>
          </div>
          <div className="flex items-center gap-4">
            <Chip
              variant={role === "admin" ? "error" : role === "teacher" ? "secondary" : "primary"}
              size="md"
            >
              {role.charAt(0).toUpperCase() + role.slice(1)}
            </Chip>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-sm">{userName}</p>
                <p className="text-xs text-[#9CA3AF]">{role}</p>
              </div>
              <div
                className="w-10 h-10 rounded-full bg-gradient-to-br flex items-center justify-center text-white"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${roleColors[role]}, ${roleColors[role]}CC)`,
                }}
              >
                {userName.charAt(0).toUpperCase()}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
