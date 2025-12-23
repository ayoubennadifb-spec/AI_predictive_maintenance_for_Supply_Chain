import { useState } from "react";
import { motion } from "motion/react";
import { ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "./Button";
import { Input, Select } from "./Input";
import { useToast } from "./Toast";

interface AuthProps {
  mode: "login" | "signup";
  onSubmit: (data: any) => void;
  onToggleMode: () => void;
  onBack: () => void;
}

export function Auth({ mode, onSubmit, onToggleMode, onBack }: AuthProps) {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    role: "student",
    school: "",
    country: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { showToast } = useToast();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    const newErrors: Record<string, string> = {};
    
    if (mode === "signup" && !formData.name) {
      newErrors.name = "Name is required";
    }
    
    if (!formData.email) {
      newErrors.email = "Email is required";
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = "Email is invalid";
    }
    
    if (!formData.password) {
      newErrors.password = "Password is required";
    } else if (formData.password.length < 8) {
      newErrors.password = "Password must be at least 8 characters";
    }
    
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    
    setErrors({});
    onSubmit(formData);
  };

  const roleOptions = [
    { value: "student", label: "Student" },
    { value: "teacher", label: "Teacher" },
    { value: "admin", label: "Administrator" },
  ];

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated Background */}
      <div className="absolute inset-0 opacity-20">
        <motion.div
          animate={{
            scale: [1, 1.2, 1],
            rotate: [0, 90, 0],
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: "linear",
          }}
          className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-[#4169E1] to-[#7C3AED] rounded-full blur-3xl"
        />
        <motion.div
          animate={{
            scale: [1, 1.3, 1],
            rotate: [0, -90, 0],
          }}
          transition={{
            duration: 25,
            repeat: Infinity,
            ease: "linear",
          }}
          className="absolute bottom-0 left-0 w-96 h-96 bg-gradient-to-tr from-[#7C3AED] to-[#4169E1] rounded-full blur-3xl"
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative z-10"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <button onClick={onBack} className="inline-flex items-center justify-center mb-4">
            <img
              src="/icodex_logo_full.svg"
              alt="ICODEX MODEL"
              className="h-24 w-auto max-w-full object-contain mix-blend-multiply"
            />
          </button>
        </div>

        {/* Form Card */}
        <div className="glass rounded-2xl p-8 shadow-2xl">
          <div className="mb-6">
            <h2 className="text-3xl mb-2">
              {mode === "login" ? "Welcome back — continue where you left off" : "Create your Icodex account"}
            </h2>
            <p className="text-[#9CA3AF]">
              {mode === "login"
                ? "Sign in and we’ll take you to your personalized dashboard."
                : "After signup, you’ll be taken to your personalized dashboard."}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "signup" && (
              <>
                <Input
                  label="Full Name"
                  type="text"
                  placeholder="John Doe"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  error={errors.name}
                />
                
                <Select
                  label="Role"
                  options={roleOptions}
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  helperText={
                    formData.role === "teacher"
                      ? "As a Teacher, you’ll upload courses and generate quizzes."
                      : formData.role === "admin"
                      ? "As an Admin, you’ll manage users, classes, and reports."
                      : "As a Student, you’ll take adaptive tests and track mastery."
                  }
                />
                <p className="text-xs text-[#6B7280]">
                  After signup, you’ll be taken to your personalized dashboard.
                </p>
              </>
            )}

            <Input
              label="Email"
              type="email"
              placeholder="you@example.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              error={errors.email}
            />

            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              error={errors.password}
              helperText={mode === "signup" ? "8+ characters, letters and numbers recommended" : undefined}
            />

            {mode === "signup" && (
              <>
                <Input
                  label="School / Institution (Optional)"
                  type="text"
                  placeholder="Stanford University"
                  value={formData.school}
                  onChange={(e) => setFormData({ ...formData, school: e.target.value })}
                />

                <Input
                  label="Country (Optional)"
                  type="text"
                  placeholder="United States"
                  value={formData.country}
                  onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                />
              </>
            )}

            <Button type="submit" variant="primary" className="w-full">
              {mode === "login" ? "Sign In" : "Create Account"}
            </Button>
          </form>

          <div className="mt-4 text-sm text-[#6B7280] flex items-center gap-2">
            <ShieldCheck size={16} className="text-[#22C55E]" />
            <span>We never share your data. Secure authentication. Used in academic settings.</span>
          </div>

          <div className="mt-6 text-center">
            <button
              onClick={onToggleMode}
              className="text-sm text-[#4169E1] hover:underline"
            >
              {mode === "login"
                ? "Don't have an account? Sign up"
                : "Already have an account? Sign in"}
            </button>
          </div>
          <div className="mt-4 text-center">
            <button onClick={onBack} className="inline-flex items-center gap-2 text-xs text-[#6B7280] hover:text-[#0F172A]">
              <Sparkles size={14} /> Back to home
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
