import { motion } from "motion/react";
import { LucideIcon } from "lucide-react";
import { Button } from "./Button";

interface HeroProps {
  title: string;
  description: string;
  primaryAction?: {
    label: string;
    icon?: LucideIcon;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    icon?: LucideIcon;
    onClick: () => void;
  };
  badge?: {
    label: string;
    variant?: "success" | "warning" | "info";
  };
}

export function Hero({ title, description, primaryAction, secondaryAction, badge }: HeroProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative glass rounded-2xl p-8 mb-8 overflow-hidden"
    >
      {/* Ambient Background */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-[#4169E1] to-[#7C3AED] rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-gradient-to-tr from-[#7C3AED] to-[#4169E1] rounded-full blur-3xl" />
      </div>

      {/* Content */}
      <div className="relative z-10">
        {badge && (
          <div className="mb-4">
            <span
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm ${
                badge.variant === "success"
                  ? "bg-[#22C55E]/10 text-[#22C55E]"
                  : badge.variant === "warning"
                  ? "bg-[#F97316]/10 text-[#F97316]"
                  : "bg-[#4169E1]/10 text-[#4169E1]"
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
              {badge.label}
            </span>
          </div>
        )}
        
        <h1 className="text-4xl mb-3">{title}</h1>
        <p className="text-lg text-[#475569] mb-6 max-w-3xl">{description}</p>
        
        {(primaryAction || secondaryAction) && (
          <div className="flex gap-3">
            {primaryAction && (
              <Button
                variant="primary"
                size="lg"
                icon={primaryAction.icon}
                onClick={primaryAction.onClick}
              >
                {primaryAction.label}
              </Button>
            )}
            {secondaryAction && (
              <Button
                variant="secondary"
                size="lg"
                icon={secondaryAction.icon}
                onClick={secondaryAction.onClick}
              >
                {secondaryAction.label}
              </Button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}
