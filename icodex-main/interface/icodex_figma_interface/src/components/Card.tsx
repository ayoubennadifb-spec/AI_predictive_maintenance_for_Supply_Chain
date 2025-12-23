import { motion } from "motion/react";
import { LucideIcon } from "lucide-react";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

export function Card({ children, className = "", hover = false, onClick }: CardProps) {
  return (
    <motion.div
      whileHover={hover ? { y: -4, boxShadow: "0 20px 40px 0 rgba(31, 38, 135, 0.15)" } : {}}
      className={`glass rounded-2xl p-6 ${onClick ? "cursor-pointer" : ""} ${className}`}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: {
    value: string;
    positive: boolean;
  };
  iconColor?: string;
}

export function StatCard({ icon: Icon, label, value, trend, iconColor = "#4169E1" }: StatCardProps) {
  return (
    <Card hover>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-[#9CA3AF] mb-2">{label}</p>
          <p className="text-3xl mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            {value}
          </p>
          {trend && (
            <p className={`text-sm ${trend.positive ? "text-[#22C55E]" : "text-[#F97316]"}`}>
              {trend.positive ? "↑" : "↓"} {trend.value}
            </p>
          )}
        </div>
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={{
            background: `linear-gradient(135deg, ${iconColor}20, ${iconColor}10)`,
          }}
        >
          <Icon size={24} style={{ color: iconColor }} />
        </div>
      </div>
    </Card>
  );
}
