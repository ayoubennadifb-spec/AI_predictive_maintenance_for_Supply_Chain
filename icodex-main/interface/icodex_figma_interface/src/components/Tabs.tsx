import { motion } from "motion/react";

interface Tab {
  id: string;
  label: string;
  count?: number;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

export function Tabs({ tabs, activeTab, onChange }: TabsProps) {
  return (
    <div className="glass rounded-xl p-1 inline-flex gap-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`relative px-6 py-2.5 rounded-lg transition-colors text-sm ${
            activeTab === tab.id ? "text-[#4169E1]" : "text-[#9CA3AF] hover:text-[#475569]"
          }`}
        >
          {activeTab === tab.id && (
            <motion.div
              layoutId="activeTab"
              className="absolute inset-0 bg-white rounded-lg shadow-sm"
              transition={{ type: "spring", duration: 0.5 }}
            />
          )}
          <span className="relative z-10 flex items-center gap-2">
            {tab.label}
            {tab.count !== undefined && (
              <span className={`px-2 py-0.5 rounded-full text-xs ${
                activeTab === tab.id ? "bg-[#4169E1]/10 text-[#4169E1]" : "bg-[#E3EBFF] text-[#9CA3AF]"
              }`}>
                {tab.count}
              </span>
            )}
          </span>
        </button>
      ))}
    </div>
  );
}

interface PillFilterProps {
  filters: { id: string; label: string; color?: string }[];
  activeFilter: string;
  onChange: (filterId: string) => void;
}

export function PillFilter({ filters, activeFilter, onChange }: PillFilterProps) {
  return (
    <div className="flex gap-2 flex-wrap">
      {filters.map((filter) => (
        <button
          key={filter.id}
          onClick={() => onChange(filter.id)}
          className={`px-4 py-2 rounded-full text-sm transition-all ${
            activeFilter === filter.id
              ? "bg-[#4169E1] text-white shadow-lg shadow-blue-500/30"
              : "glass text-[#475569] hover:bg-[#E3EBFF]"
          }`}
          style={
            activeFilter === filter.id && filter.color
              ? { backgroundColor: filter.color, boxShadow: `0 4px 12px ${filter.color}30` }
              : {}
          }
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
