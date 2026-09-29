import { useEffect } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

export default function PremiumEffects() {
  const x = useMotionValue(-100);
  const y = useMotionValue(-100);

  const smoothX = useSpring(x, {
    stiffness: 80,
    damping: 32,
    mass: 0.45,
  });

  const smoothY = useSpring(y, {
    stiffness: 80,
    damping: 32,
    mass: 0.45,
  });

  useEffect(() => {
    let frame = 0;

    const move = (event: PointerEvent) => {
      cancelAnimationFrame(frame);

      frame = requestAnimationFrame(() => {
        x.set(event.clientX);
        y.set(event.clientY);
      });
    };

    window.addEventListener("pointermove", move, { passive: true });

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
    };
  }, [x, y]);

  return (
    <>
      <motion.div
        aria-hidden="true"
        className="pointer-events-none fixed z-[9998] hidden lg:block"
        style={{
          left: smoothX,
          top: smoothY,
          width: 90,
          height: 90,
          translateX: "-50%",
          translateY: "-50%",
          borderRadius: "999px",
          background:
            "radial-gradient(circle, rgba(255,170,110,.022) 0%, rgba(255,170,110,.008) 35%, transparent 72%)",
          filter: "blur(10px)",
        }}
      />

      <motion.div
        aria-hidden="true"
        className="pointer-events-none fixed z-[9997] hidden lg:block"
        style={{
          left: smoothX,
          top: smoothY,
          width: 9,
          height: 9,
          translateX: "-50%",
          translateY: "-50%",
          borderRadius: "999px",
          border: "1px solid rgba(255,170,110,.09)",
        }}
      />
    </>
  );
}
