import { useEffect, useRef, useState } from "react";
import { getJob } from "../api/client";
import type { JobStatusResponse } from "../types/extraction";

const POLL_INTERVAL_MS = 2000;

interface JobStatusBannerProps {
  jobId: string;
  onSettled: (job: JobStatusResponse) => void;
}

export default function JobStatusBanner({ jobId, onSettled }: JobStatusBannerProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    startedAt.current = Date.now();
    let cancelled = false;

    async function poll() {
      const job = await getJob(jobId);
      if (cancelled) return;
      if (job.status === "succeeded" || job.status === "failed") {
        onSettled(job);
        return;
      }
      setTimeout(poll, POLL_INTERVAL_MS);
    }

    const tick = setInterval(() => {
      setElapsedSeconds(Math.round((Date.now() - startedAt.current) / 1000));
    }, 1000);

    poll();

    return () => {
      cancelled = true;
      clearInterval(tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return (
    <p style={{ color: "#555" }}>
      Processing... ({elapsedSeconds}s elapsed - parsing, table stitching, retrieval and the LLM
      call can take a few minutes)
    </p>
  );
}
