/**
 * Job queue endpoints for background forensics workers.
 *
 * POST /v1/jobs/claim        — claim next queued analysis job (SKIP LOCKED)
 * POST /v1/jobs/:id/complete — submit finished analysis result
 */
import { Router } from 'express';
import { getAnalysisService } from '../services/analyses.js';
import { getPrisma } from '../config/prisma.js';

export const jobsRouter = Router();

jobsRouter.post('/claim', async (req, res, next) => {
  try {
    const workerId = req.body?.workerId || 'worker-unknown';
    const service = getAnalysisService();
    const claimed = await service.claimNextJob(workerId);
    if (!claimed) {
      return res.status(200).json({ job: null });
    }

    // Load image buffer to send to worker
    const prisma = getPrisma();
    const analysis = await prisma.analysis.findUnique({
      where: { id: claimed.analysisId },
      include: { image: true, referenceImage: true },
    });

    if (!analysis) {
      return res.status(200).json({ job: null });
    }

    const path = await import('node:path');
    const fs = await import('node:fs/promises');
    const localRoot = path.resolve(process.cwd(), '.local-storage');

    let suspectHex = '';
    try {
      const buf = await fs.readFile(path.join(localRoot, 'originals', analysis.image.storagePath));
      suspectHex = buf.toString('hex');
    } catch {
      // File could not be read
    }

    let referenceHex: string | null = null;
    if (analysis.referenceImage) {
      try {
        const refBuf = await fs.readFile(path.join(localRoot, 'originals', analysis.referenceImage.storagePath));
        referenceHex = refBuf.toString('hex');
      } catch {}
    }

    res.json({
      job: {
        id: claimed.jobId,
        analysisId: claimed.analysisId,
        pipeline: claimed.pipeline,
        imageHex: suspectHex,
        referenceHex,
      },
    });
  } catch (err) {
    next(err);
  }
});

jobsRouter.post('/:id/complete', async (req, res, next) => {
  try {
    const { analysisId, result } = req.body;
    const service = getAnalysisService();
    await service.persistAnalysisResult(analysisId, result);
    res.json({ success: true });
  } catch (err) {
    next(err);
  }
});

