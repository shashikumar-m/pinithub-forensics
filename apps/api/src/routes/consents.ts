/**
 * Consent routes — records user consent before image processing.
 *
 * POST /v1/consents — record consent
 *
 * Consent is required before any image capture/upload. The consent
 * record includes version info so the consent text can be changed
 * later without rewriting the application.
 */
import { Router } from 'express';
import { getPrisma } from '../config/prisma.js';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { createConsentSchema } from '../schemas/index.js';
import { getLogger } from '../config/logger.js';
import type { ConsentResponse } from '@pinithub/shared';

export const consentsRouter = Router();

consentsRouter.post(
  '/',
  validate(createConsentSchema, 'body'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const body = req.body;
      const log = getLogger();

      const prisma = getPrisma();
      const consent = await prisma.consentRecord.create({
        data: {
          ownerId,
          consentGiven: true,
          consentVersion: body.consentVersion,
          policyVersion: body.policyVersion ?? null,
          sourceType: body.sourceType,
        },
      });

      log.info({ consentId: consent.id, ownerId, sourceType: body.sourceType }, 'Consent recorded');

      const response: ConsentResponse = {
        consent: {
          id: consent.id,
          consentGiven: consent.consentGiven,
          consentVersion: consent.consentVersion,
          timestamp: consent.timestamp.toISOString(),
        },
      };
      res.status(201).json(response);
    } catch (err) {
      next(err);
    }
  },
);
