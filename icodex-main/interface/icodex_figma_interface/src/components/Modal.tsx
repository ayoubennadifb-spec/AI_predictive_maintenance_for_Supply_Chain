import { motion, AnimatePresence } from "motion/react";
import { X } from "lucide-react";
import { Button } from "./Button";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}

export function Modal({ isOpen, onClose, title, description, children, footer, size = "md" }: ModalProps) {
  const sizes = {
    sm: "max-w-md",
    md: "max-w-2xl",
    lg: "max-w-4xl",
    xl: "max-w-6xl",
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-md z-40"
            onClick={onClose}
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ type: "spring", duration: 0.3 }}
              className={`glass rounded-2xl shadow-2xl w-full ${sizes[size]} max-h-[90vh] overflow-hidden flex flex-col`}
            >
              {/* Header */}
              <div className="flex items-start justify-between p-6 border-b border-[#1E293B]/10">
                <div className="flex-1">
                  <h3 className="text-2xl mb-1">{title}</h3>
                  {description && <p className="text-[#9CA3AF]">{description}</p>}
                </div>
                <button
                  onClick={onClose}
                  aria-label="Close"
                  className="text-[#9CA3AF] hover:text-[#475569] transition-colors ml-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4169E1]/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white/80"
                >
                  <X size={24} />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-6">
                {children}
              </div>

              {/* Footer */}
              {footer && (
                <div className="flex items-center justify-end gap-3 p-6 border-t border-[#1E293B]/10">
                  {footer}
                </div>
              )}
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
