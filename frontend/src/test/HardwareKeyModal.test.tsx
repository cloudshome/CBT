import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { HardwareKeyModal } from '../components/HardwareKeyModal';
import * as api from '../services/api';

vi.mock('../services/api', () => ({
  getHardwareKeyStatus: vi.fn(),
  getHardwareKeyAuthOptions: vi.fn(),
  verifyHardwareKeyAuth: vi.fn(),
  getHardwareKeyRegisterOptions: vi.fn(),
  verifyHardwareKeyRegister: vi.fn(),
  revokeHardwareKeyCredential: vi.fn(),
  revokeHardwareKeyClearance: vi.fn(),
}));

describe('HardwareKeyModal Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getHardwareKeyStatus).mockResolvedValue({
      status: 'OK',
      hardware_auth_configured: true,
      registered_credentials_count: 1,
      registered_credentials: [
        {
          credential_id: 'cred_test_123',
          label: 'YubiKey 5C Primary',
          created_at: 1729000000,
          last_used_at: 1729010000,
          sign_count: 42,
          backup_eligible: true,
          backup_state: true,
        },
      ],
      active_clearance: null,
      gate8_requires_clearance: true,
      execution_mode: 'PAPER_TRADING',
      server_time_utc: Date.now() / 1000,
    });
  });

  it('renders nothing when isOpen is false', () => {
    const handleClose = vi.fn();
    const { container } = render(
      <HardwareKeyModal isOpen={false} onClose={handleClose} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal dialog when isOpen is true', async () => {
    const handleClose = vi.fn();
    render(<HardwareKeyModal isOpen={true} onClose={handleClose} />);

    await waitFor(() => {
      expect(screen.getByText('Human Live Execution Clearance')).toBeInTheDocument();
    });

    expect(screen.getByText('CLASS H BOUNDARY')).toBeInTheDocument();
    expect(screen.getByText(/Physical Hardware Key \(WebAuthn \/ FIDO2\) Verification/i)).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    const handleClose = vi.fn();
    const { container } = render(<HardwareKeyModal isOpen={true} onClose={handleClose} />);

    await waitFor(() => {
      expect(screen.getByText('Human Live Execution Clearance')).toBeInTheDocument();
    });

    const closeBtn = container.querySelector('button .lucide-x')?.closest('button');
    expect(closeBtn).toBeDefined();
    if (closeBtn) {
      fireEvent.click(closeBtn);
      expect(handleClose).toHaveBeenCalled();
    }
  });

  it('switches to Manage & Enroll Keys tab upon clicking tab', async () => {
    const handleClose = vi.fn();
    render(<HardwareKeyModal isOpen={true} onClose={handleClose} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Manage & Enroll Keys/i })).toBeInTheDocument();
    });

    const enrollTab = screen.getByRole('button', { name: /Manage & Enroll Keys/i });
    fireEvent.click(enrollTab);

    await waitFor(() => {
      expect(screen.getByText(/Enroll New WebAuthn Authenticator/i)).toBeInTheDocument();
    });
  });
});
