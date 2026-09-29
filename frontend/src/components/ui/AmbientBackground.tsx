import { useEffect, useRef } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

export default function AmbientBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const smoothX = useSpring(mouseX, {
    stiffness: 55,
    damping: 20,
    mass: 0.5,
  });

  const smoothY = useSpring(mouseY, {
    stiffness: 55,
    damping: 20,
    mass: 0.5,
  });

  useEffect(() => {
    const handleMove = (event: MouseEvent) => {
      mouseX.set(event.clientX);
      mouseY.set(event.clientY);
    };

    window.addEventListener("mousemove", handleMove, { passive: true });

    return () => {
      window.removeEventListener("mousemove", handleMove);
    };
  }, [mouseX, mouseY]);

  return (
    <div
      ref={containerRef}
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
      aria-hidden="true"
    >
      {/* Very subtle grid */}
      <div className="absolute inset-0 app-grid opacity-50" />

      {/* Ambient blobs */}
      <motion.div
        className="absolute -top-48 -left-40 h-[520px] w-[520px] rounded-full bg-orange-200/20 blur-[120px]"
        style={{
          x: smoothX,
          y: smoothY,
        }}
      />

      <motion.div
        className="absolute right-[-180px] top-[15%] h-[520px] w-[520px] rounded-full bg-blue-200/15 blur-[130px]"
        style={{
          x: useMotionValue(0),
          y: smoothY,
        }}
      />

      {/* Cursor spotlight */}
      <motion.div
        className="absolute h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          left: smoothX,
          top: smoothY,
          background:
            "radial-gradient(circle, rgba(255,255,255,0.62) 0%, rgba(255,255,255,0.18) 32%, transparent 72%)",
          filter: "blur(8px)",
        }}
      />
    </div>
  );
}
