import { motion } from "motion/react";

interface Column<T> {
  key: keyof T | string;
  label: React.ReactNode;
  render?: (item: T) => React.ReactNode;
}

interface TableProps<T> {
  data: T[];
  columns: Column<T>[];
  onRowClick?: (item: T) => void;
  loading?: boolean;
}

export function Table<T extends Record<string, any>>({ data, columns, onRowClick, loading }: TableProps<T>) {
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#1E293B]/10">
              {columns.map((column) => (
                <th
                  key={column.key as string}
                  className="px-6 py-4 text-left text-sm text-[#9CA3AF] uppercase tracking-wider"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-12 text-center text-[#9CA3AF]">
                  Loading...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-12 text-center text-[#9CA3AF]">
                  No data available
                </td>
              </tr>
            ) : (
              data.map((item, index) => (
                <motion.tr
                  key={index}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className={`border-b border-[#1E293B]/5 ${
                    onRowClick ? "cursor-pointer hover:bg-[#E3EBFF]/30" : ""
                  } transition-colors`}
                  onClick={() => onRowClick?.(item)}
                >
                  {columns.map((column) => (
                    <td key={column.key as string} className="px-6 py-4 text-sm text-[#0F172A]">
                      {column.render ? column.render(item) : item[column.key as keyof T]}
                    </td>
                  ))}
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
