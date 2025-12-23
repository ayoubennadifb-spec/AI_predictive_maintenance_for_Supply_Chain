import { LucideIcon } from "lucide-react";

interface ChipProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "error" | "info" | "default" | "primary" | "secondary";
  icon?: LucideIcon;
  size?: "sm" | "md";
}

export function Chip({ children, variant = "default", icon: Icon, size = "md" }: ChipProps) {
  const variants = {
    success: "bg-[#22C55E]/10 text-[#22C55E] border-[#22C55E]/20",
    warning: "bg-[#F97316]/10 text-[#F97316] border-[#F97316]/20",
    error: "bg-[#EF4444]/10 text-[#EF4444] border-[#EF4444]/20",
    info: "bg-[#4169E1]/10 text-[#4169E1] border-[#4169E1]/20",
    primary: "bg-[#4169E1]/10 text-[#4169E1] border-[#4169E1]/20",
    secondary: "bg-[#7C3AED]/10 text-[#7C3AED] border-[#7C3AED]/20",
    default: "bg-[#E3EBFF] text-[#475569] border-[#E3EBFF]",
  };

  const sizes = {
    sm: "px-2 py-1 text-xs",
    md: "px-3 py-1.5 text-sm",
  };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border ${variants[variant]} ${sizes[size]}`}>
      {Icon && <Icon size={size === "sm" ? 12 : 14} />}
      {children}
    </span>
  );
}

interface StatusChipProps {
  status?: "processing" | "ready" | "failed" | "pending" | "not_started" | "in_progress" | "completed" | "approved";
}

export function StatusChip({ status }: StatusChipProps) {
  const statusConfig = {
    processing: { label: "Processing", variant: "warning" as const, icon: "?" },
    ready: { label: "Ready", variant: "success" as const, icon: "?" },
    failed: { label: "Failed", variant: "error" as const, icon: "?" },
    pending: { label: "Pending Review", variant: "warning" as const, icon: "?" },
    not_started: { label: "Not Started", variant: "default" as const, icon: "•" },
    in_progress: { label: "In Progress", variant: "info" as const, icon: "?" },
    completed: { label: "Completed", variant: "success" as const, icon: "?" },
    approved: { label: "Approved", variant: "success" as const, icon: "?" },
  } as const;

  const fallback = { label: "Unknown", variant: "default" as const, icon: "•" };
  const config = (status ? statusConfig[status] : undefined) || fallback;

  return (
    <Chip variant={config.variant} size="sm">
      <span>{config.icon}</span>
      {config.label}
    </Chip>
  );
}