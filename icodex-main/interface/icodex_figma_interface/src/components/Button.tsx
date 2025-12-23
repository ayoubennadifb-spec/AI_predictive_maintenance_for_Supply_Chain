import { motion } from "motion/react";
import { LucideIcon } from "lucide-react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "tertiary" | "destructive";
  size?: "sm" | "md" | "lg";
  icon?: LucideIcon;
  iconPosition?: "left" | "right";
  children: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  icon: Icon,
  iconPosition = "left",
  children,
  className = "",
  disabled = false,
  ...props
}: ButtonProps) {
  const baseClasses =
    "inline-flex items-center justify-center gap-2 rounded-xl transition-all duration-200 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4169E1]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#F5F7FB]";
  
  const variants = {
    primary: disabled
      ? "bg-gray-300 text-gray-500 cursor-not-allowed"
      : "bg-gradient-to-r from-[#4169E1] to-[#5B7FE8] text-white shadow-lg shadow-blue-500/30 hover:shadow-xl hover:shadow-blue-500/40 hover:-translate-y-0.5",
    secondary: disabled
      ? "border border-gray-300 text-gray-400 cursor-not-allowed"
      : "glass border-2 border-[#4169E1] text-[#4169E1] hover:bg-[#4169E1] hover:text-white hover:-translate-y-0.5",
    tertiary: disabled
      ? "text-gray-400 cursor-not-allowed"
      : "text-[#4169E1] hover:bg-[#E3EBFF] hover:text-[#4169E1]",
    destructive: disabled
      ? "bg-gray-300 text-gray-500 cursor-not-allowed"
      : "bg-[#EF4444] text-white shadow-lg shadow-red-500/30 hover:shadow-xl hover:shadow-red-500/40 hover:-translate-y-0.5",
  };

  const sizes = {
    sm: "px-4 py-2 text-sm",
    md: "px-6 py-3 text-base",
    lg: "px-8 py-4 text-lg",
  };

  return (
    <motion.button
      whileHover={!disabled ? { scale: 1.02 } : {}}
      whileTap={!disabled ? { scale: 0.98 } : {}}
      className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {Icon && iconPosition === "left" && <Icon size={18} />}
      {children}
      {Icon && iconPosition === "right" && <Icon size={18} />}
    </motion.button>
  );
}
