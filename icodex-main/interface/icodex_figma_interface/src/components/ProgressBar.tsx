import { motion } from "motion/react";

interface ProgressBarProps {
  progress: number;
  showLabel?: boolean;
  className?: string;
}

export function ProgressBar({ progress, showLabel = true, className = "" }: ProgressBarProps) {
  return (
    <div className={`w-full ${className}`}>
      {showLabel && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-[#475569]">Progress</span>
          <span className="text-sm text-[#4169E1]">{progress}%</span>
        </div>
      )}
      <div className="h-2 bg-[#E3EBFF] rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="h-full bg-gradient-to-r from-[#4169E1] to-[#7C3AED] rounded-full"
        />
      </div>
    </div>
  );
}

interface StepperProps {
  steps: string[];
  currentStep: number;
}

export function Stepper({ steps, currentStep }: StepperProps) {
  return (
    <div className="flex items-center justify-between">
      {steps.map((step, index) => (
        <div key={step} className="flex items-center flex-1">
          <div className="flex flex-col items-center">
            <motion.div
              initial={{ scale: 0.8 }}
              animate={{ 
                scale: index === currentStep ? 1.1 : 1,
                backgroundColor: index <= currentStep ? "#4169E1" : "#E3EBFF"
              }}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
                index <= currentStep ? "text-white" : "text-[#9CA3AF]"
              }`}
            >
              {index < currentStep ? "✓" : index + 1}
            </motion.div>
            <p className={`mt-2 text-sm ${index <= currentStep ? "text-[#4169E1]" : "text-[#9CA3AF]"}`}>
              {step}
            </p>
          </div>
          {index < steps.length - 1 && (
            <div className="flex-1 h-0.5 bg-[#E3EBFF] mx-4 relative overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: index < currentStep ? "100%" : "0%" }}
                transition={{ duration: 0.5 }}
                className="absolute inset-0 bg-[#4169E1]"
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
