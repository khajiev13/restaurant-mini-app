import { useCallback, useEffect, useRef, useState } from 'react';
import { getMe } from '../services/api';
import { useAuthStore } from '../stores/authStore';

export type PhoneVerificationStatus =
  | 'ready'
  | 'requesting'
  | 'verifying'
  | 'declined'
  | 'delayed'
  | 'unsupported'
  | 'outside_telegram'
  | 'network_error';

export interface PhoneVerificationController {
  status: PhoneVerificationStatus;
  requestPhone: () => void;
  checkAgain: () => Promise<void>;
}

const PROFILE_POLL_INTERVAL_MS = 1_500;
const MAX_PROFILE_REQUESTS = 10;
let automaticRequestClaimed = false;

type PhoneVerificationEnvironment =
  | { status: 'ready'; requestContact: (callback: (shared: boolean) => void) => void }
  | { status: 'unsupported' | 'outside_telegram' };

function classifyPhoneVerificationEnvironment(): PhoneVerificationEnvironment {
  const telegram = window.Telegram?.WebApp;
  if (!telegram || typeof telegram.initData !== 'string' || !telegram.initData.trim()) {
    return { status: 'outside_telegram' };
  }

  if (typeof telegram.requestContact !== 'function' || typeof telegram.isVersionAtLeast !== 'function') {
    return { status: 'unsupported' };
  }
  const requestContact = telegram.requestContact.bind(telegram);

  try {
    if (telegram.isVersionAtLeast('6.9') !== true) {
      return { status: 'unsupported' };
    }
  } catch {
    return { status: 'unsupported' };
  }

  return {
    status: 'ready',
    requestContact,
  };
}

export function usePhoneVerification({
  autoRequest,
}: {
  autoRequest: boolean;
}): PhoneVerificationController {
  const [status, setStatus] = useState<PhoneVerificationStatus>(
    () => classifyPhoneVerificationEnvironment().status,
  );
  const acceptVerifiedProfile = useAuthStore((state) => state.acceptVerifiedProfile);
  const mountedRef = useRef(true);
  const pollCycleRef = useRef(0);
  const promptCycleRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resolveTimerRef = useRef<(() => void) | null>(null);

  const clearPendingTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    resolveTimerRef.current?.();
    resolveTimerRef.current = null;
  }, []);

  const pollProfile = useCallback(async () => {
    const cycle = ++pollCycleRef.current;
    clearPendingTimer();
    if (mountedRef.current) {
      setStatus('verifying');
    }

    let receivedUnverifiedProfile = false;
    for (let attempt = 0; attempt < MAX_PROFILE_REQUESTS; attempt += 1) {
      try {
        const response = await getMe();
        if (!mountedRef.current || pollCycleRef.current !== cycle) {
          return;
        }

        const profile = response.data.data;
        if (profile.phone_verified) {
          acceptVerifiedProfile(profile);
          return;
        }
        receivedUnverifiedProfile = true;
      } catch {
        if (!mountedRef.current || pollCycleRef.current !== cycle) {
          return;
        }
      }

      if (attempt < MAX_PROFILE_REQUESTS - 1) {
        await new Promise<void>((resolve) => {
          resolveTimerRef.current = resolve;
          timerRef.current = setTimeout(() => {
            timerRef.current = null;
            resolveTimerRef.current = null;
            resolve();
          }, PROFILE_POLL_INTERVAL_MS);
        });
        if (!mountedRef.current || pollCycleRef.current !== cycle) {
          return;
        }
      }
    }

    if (mountedRef.current && pollCycleRef.current === cycle) {
      setStatus(receivedUnverifiedProfile ? 'delayed' : 'network_error');
    }
  }, [acceptVerifiedProfile, clearPendingTimer]);

  const requestPhone = useCallback(() => {
    const promptCycle = ++promptCycleRef.current;
    pollCycleRef.current += 1;
    clearPendingTimer();

    const environment = classifyPhoneVerificationEnvironment();
    if (environment.status !== 'ready') {
      setStatus(environment.status);
      return;
    }

    setStatus('requesting');
    try {
      environment.requestContact((shared) => {
        if (!mountedRef.current || promptCycleRef.current !== promptCycle) {
          return;
        }
        if (!shared) {
          setStatus('declined');
          return;
        }
        void pollProfile();
      });
    } catch {
      setStatus('unsupported');
    }
  }, [clearPendingTimer, pollProfile]);

  const checkAgain = useCallback(async () => {
    const environment = classifyPhoneVerificationEnvironment();
    if (environment.status !== 'ready') {
      pollCycleRef.current += 1;
      clearPendingTimer();
      setStatus(environment.status);
      return;
    }
    await pollProfile();
  }, [clearPendingTimer, pollProfile]);

  const requestPhoneRef = useRef(requestPhone);
  requestPhoneRef.current = requestPhone;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      promptCycleRef.current += 1;
      pollCycleRef.current += 1;
      clearPendingTimer();
    };
  }, [clearPendingTimer]);

  useEffect(() => {
    if (!autoRequest || automaticRequestClaimed) {
      return;
    }
    automaticRequestClaimed = true;
    requestPhoneRef.current();
  }, [autoRequest]);

  return {
    status,
    requestPhone,
    checkAgain,
  };
}
