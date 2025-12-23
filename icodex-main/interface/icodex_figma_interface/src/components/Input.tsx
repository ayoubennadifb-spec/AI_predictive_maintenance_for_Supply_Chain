import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Input({ label, error, helperText, className = "", ...props }: InputProps) {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = props.type === "password";

  return (
    <div className="w-full">
      {label && (
        <label className="block mb-2 text-sm text-[#475569]">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          {...props}
          type={isPassword && showPassword ? "text" : props.type}
          className={`
            w-full px-4 py-3 rounded-xl glass border-2 
            ${error ? "border-[#EF4444]" : "border-transparent focus:border-[#4169E1]"} 
            transition-all duration-200 outline-none
            text-[#0F172A] placeholder:text-[#9CA3AF]
            ${className}
          `}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#475569]"
          >
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-sm text-[#EF4444]">{error}</p>}
      {helperText && !error && <p className="mt-1 text-sm text-[#9CA3AF]">{helperText}</p>}
    </div>
  );
}

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function TextArea({ label, error, helperText, className = "", ...props }: TextAreaProps) {
  return (
    <div className="w-full">
      {label && (
        <label className="block mb-2 text-sm text-[#475569]">
          {label}
        </label>
      )}
      <textarea
        {...props}
        className={`
          w-full px-4 py-3 rounded-xl glass border-2 
          ${error ? "border-[#EF4444]" : "border-transparent focus:border-[#4169E1]"} 
          transition-all duration-200 outline-none
          text-[#0F172A] placeholder:text-[#9CA3AF]
          resize-none
          ${className}
        `}
      />
      {error && <p className="mt-1 text-sm text-[#EF4444]">{error}</p>}
      {helperText && !error && <p className="mt-1 text-sm text-[#9CA3AF]">{helperText}</p>}
    </div>
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
  options: { value: string; label: string }[];
}

export function Select({ label, error, helperText, options, className = "", ...props }: SelectProps) {
  return (
    <div className="w-full">
      {label && (
        <label className="block mb-2 text-sm text-[#475569]">
          {label}
        </label>
      )}
      <select
        {...props}
        className={`
          w-full px-4 py-3 rounded-xl glass border-2 
          ${error ? "border-[#EF4444]" : "border-transparent focus:border-[#4169E1]"} 
          transition-all duration-200 outline-none
          text-[#0F172A]
          ${className}
        `}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="mt-1 text-sm text-[#EF4444]">{error}</p>}
      {helperText && !error && <p className="mt-1 text-sm text-[#9CA3AF]">{helperText}</p>}
    </div>
  );
}
