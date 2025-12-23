import { motion } from "motion/react";
import {
  Sparkles,
  Target,
  BarChart3,
  ArrowRight,
  CheckCircle,
  ShieldCheck,
  Users,
  BookOpen,
  Brain,
  Upload,
  LineChart,
} from "lucide-react";
import { Button } from "./Button";
import { Chip } from "./Chip";

interface LandingProps {
  onLogin: () => void;
  onSignup: () => void;
}

export function Landing({ onLogin, onSignup }: LandingProps) {
  const roleBlocks = [
    {
      title: "Students",
      pain: "Not sure what to study next.",
      solve: "Adaptive quizzes + mastery map after every attempt.",
      inside: ["Weak concept highlights", "Next best practice", "Instant feedback"],
    },
    {
      title: "Teachers",
      pain: "Manual quiz building and slow grading.",
      solve: "Upload PDFs, auto-generate quizzes, assign in minutes.",
      inside: ["Concept coverage chips", "Bloom/difficulty spread", "Auto-evaluated attempts"],
    },
    {
      title: "Admins / Institutions",
      pain: "No visibility into risk and program health.",
      solve: "Concept-level dashboards, risk signals, audit trails.",
      inside: ["Class health view", "At-risk student flags", "Exportable reports"],
    },
  ];

  const steps = [
    { icon: Upload, title: "Upload material", text: "PDF/PPT course files drop right in." },
    { icon: Sparkles, title: "AI generates quizzes", text: "Adaptive, with difficulty + Bloom coverage." },
    { icon: Target, title: "Students take assessments", text: "Personalized flow with feedback per question." },
    { icon: BarChart3, title: "Mastery & misconceptions", text: "Concept map, risk signals, and actions." },
  ];

  const proof = [
    { icon: Brain, label: "Concept mastery", value: "Per-concept accuracy + confidence" },
    { icon: LineChart, label: "Adaptive paths", value: "Adjusts by pacing + correctness" },
    { icon: ShieldCheck, label: "Trusted", value: "Built for real classrooms" },
  ];

  return (
    <div className="min-h-screen relative overflow-hidden">
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

      {/* Header */}
      <nav className="relative z-10 glass border-b border-[#1E293B]/10">
        <div className="max-w-7xl mx-auto px-8 py-4 flex items-center justify-between">
          <div className="flex items-center">
            <img
              src="/icodex_logo_full.svg"
              alt="ICODEX MODEL"
              className="h-14 w-auto max-w-full object-contain mix-blend-multiply"
            />
          </div>
          <div className="flex gap-3">
            <Button variant="tertiary" onClick={onLogin}>
              Login
            </Button>
            <Button variant="primary" onClick={onSignup}>
              Get Started
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="relative z-10 max-w-7xl mx-auto px-8 py-20" id="top">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: "spring" }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#4169E1]/10 text-[#4169E1] mb-6"
          >
            <Sparkles size={16} />
            <span className="text-sm">AI-Powered Adaptive Quizzes</span>
          </motion.div>
          
          <h1 className="text-6xl mb-6 leading-tight">
            Master courses faster with
            <br />
            <span className="bg-gradient-to-r from-[#4169E1] to-[#7C3AED] bg-clip-text text-transparent">
              adaptive AI assessments
            </span>
          </h1>
          
          <p className="text-xl text-[#475569] mb-8 max-w-3xl mx-auto">
            Upload course materials, generate adaptive quizzes, and surface mastery and misconceptions in minutes.
            Built for students, teachers, and admins who need answers fast.
          </p>
          
          <div className="flex gap-4 justify-center">
            <Button variant="primary" size="lg" icon={ArrowRight} iconPosition="right" onClick={onSignup}>
              Get Started Free
            </Button>
            <Button variant="secondary" size="lg" onClick={() => {
              const el = document.getElementById("how-it-works");
              if (el) el.scrollIntoView({ behavior: "smooth" });
            }}>
              See How It Works
            </Button>
          </div>
          <p className="text-sm text-[#6B7280] mt-3">Start free, no credit card • You’ll see your dashboard after signup</p>
        </motion.div>

        {/* Role-Based Value */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
          {roleBlocks.map((block, idx) => (
            <motion.div
              key={block.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + idx * 0.1 }}
            >
              <div className="glass rounded-2xl p-6 h-full flex flex-col gap-3 hover:shadow-xl transition-shadow">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl">{block.title}</h3>
                  <Chip icon={Users} label={block.title === "Admins / Institutions" ? "Oversight" : "Personalized"} />
                </div>
                <div className="text-sm text-[#9CA3AF]">Pain: {block.pain}</div>
                <div className="text-sm font-semibold text-[#0F172A]">Solution: {block.solve}</div>
                <div className="text-xs uppercase text-[#9CA3AF] tracking-wide mt-2">Inside you&apos;ll see</div>
                <div className="space-y-2">
                  {block.inside.map((item) => (
                    <div key={item} className="flex items-center gap-2 text-sm text-[#475569]">
                      <CheckCircle size={16} className="text-[#22C55E]" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        {/* How It Works */}
        <div id="how-it-works" className="glass rounded-2xl p-8 mb-16">
          <div className="flex items-center justify-between mb-6 gap-3">
            <div>
              <p className="text-xs text-[#9CA3AF] uppercase">How it works</p>
              <h2 className="text-3xl">From upload to mastery in four steps</h2>
            </div>
            <Button variant="secondary" onClick={onSignup}>Get Started Free</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {steps.map((step, idx) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="glass rounded-2xl p-4 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="w-10 h-10 rounded-xl bg-[#4169E1]/10 flex items-center justify-center">
                      <Icon size={20} className="text-[#4169E1]" />
                    </div>
                    <span className="text-xs text-[#9CA3AF]">0{idx + 1}</span>
                  </div>
                  <h3 className="text-lg">{step.title}</h3>
                  <p className="text-sm text-[#475569]">{step.text}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Proof Section */}
        <div className="grid md:grid-cols-2 gap-6 mb-16">
          <div className="glass rounded-2xl p-8 bg-gradient-to-br from-[#4169E1]/10 to-[#7C3AED]/10">
            <h3 className="text-2xl mb-3">See the platform you get</h3>
            <p className="text-sm text-[#475569] mb-4">
              Concept mastery maps, misconception clusters, class health, and audit trails for every role.
            </p>
            <div className="aspect-[4/3] rounded-xl bg-white/60 border border-white/50 flex items-center justify-center text-[#9CA3AF]">
              Screenshot placeholder
            </div>
          </div>
          <div className="glass rounded-2xl p-8">
            <h3 className="text-2xl mb-4">Built for trust</h3>
            <div className="space-y-3">
              {proof.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label} className="flex items-center gap-3 p-3 rounded-xl bg-[#F8FAFF]">
                    <div className="w-10 h-10 rounded-lg bg-[#4169E1]/10 flex items-center justify-center">
                      <Icon size={18} className="text-[#4169E1]" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{item.label}</p>
                      <p className="text-xs text-[#6B7280]">{item.value}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 text-sm text-[#475569] space-y-1">
              <div className="flex items-center gap-2"><ShieldCheck size={16} className="text-[#22C55E]" />Secure authentication; data not shared.</div>
              <div className="flex items-center gap-2"><BookOpen size={16} className="text-[#4169E1]" />Designed with educators; works for students, teachers, admins.</div>
            </div>
          </div>
        </div>

        {/* Conversion Reinforcement */}
        <div className="glass rounded-2xl p-6 flex flex-col md:flex-row items-center justify-between gap-4 border border-[#4169E1]/20">
          <div>
            <p className="text-lg font-semibold">Ready to try Icodex?</p>
            <p className="text-sm text-[#475569]">Start free, no credit card • You&apos;ll land in your personalized dashboard.</p>
          </div>
          <div className="flex gap-3">
            <Button variant="primary" onClick={onSignup}>Get Started Free</Button>
            <Button variant="secondary" onClick={onLogin}>Sign In</Button>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="relative z-10 glass border-t border-[#1E293B]/10 mt-20">
        <div className="max-w-7xl mx-auto px-8 py-8 text-center text-[#9CA3AF] space-y-2">
          <div className="flex items-center justify-center gap-4 text-sm flex-wrap">
            <span>Start free, no credit card</span>
            <span className="text-[#D1D5DB]">•</span>
            <span>Works for students, teachers, and admins</span>
            <span className="text-[#D1D5DB]">•</span>
            <span>Your data stays secure</span>
          </div>
          <p>© 2025 ICodex Model. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
