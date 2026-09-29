import React from 'react';

interface SkeletonProps {
  className?: string;
}

export const LoadingSkeleton: React.FC<SkeletonProps> = ({ className = 'h-6 w-full' }) => {
  return (
    <div
      className={`animate-pulse bg-slate-800/60 rounded border border-slate-700/30 ${className}`}
    />
  );
};
