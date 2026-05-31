import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { renderHook } from '@testing-library/react';
import { ConfirmationCard } from '../ConfirmationCard';
import { useToolTrace } from '../useToolTrace';

vi.mock('../../../services/api', () => ({
  apiService: {
    resolveMcpConfirmation: vi.fn(),
  },
}));

import { apiService } from '../../../services/api';

const _basePending = {
  traceId: 'trace-123',
  serverId: 'mpc_pro',
  tool: 'ingest_stac_item',
  tier: 'write' as const,
  args: { item: 'foo' },
};

describe('ConfirmationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders tool name and tier badge', () => {
    render(<ConfirmationCard pending={_basePending} onResolved={vi.fn()} />);
    expect(screen.getByText(/WRITE action/i)).toBeInTheDocument();
    expect(screen.getByText('ingest_stac_item')).toBeInTheDocument();
    expect(screen.getByText('mpc_pro')).toBeInTheDocument();
  });

  it('POSTs approval and calls onResolved(true)', async () => {
    (apiService.resolveMcpConfirmation as any).mockResolvedValue(true);
    const onResolved = vi.fn();
    render(<ConfirmationCard pending={_basePending} onResolved={onResolved} />);
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(apiService.resolveMcpConfirmation).toHaveBeenCalledWith('trace-123', true);
      expect(onResolved).toHaveBeenCalledWith('trace-123', true);
    });
  });

  it('POSTs denial and calls onResolved(false)', async () => {
    (apiService.resolveMcpConfirmation as any).mockResolvedValue(true);
    const onResolved = vi.fn();
    render(<ConfirmationCard pending={_basePending} onResolved={onResolved} />);
    fireEvent.click(screen.getByRole('button', { name: /deny/i }));
    await waitFor(() => {
      expect(apiService.resolveMcpConfirmation).toHaveBeenCalledWith('trace-123', false);
      expect(onResolved).toHaveBeenCalledWith('trace-123', false);
    });
  });

  it('shows expired warning when broker returns false (no pending)', async () => {
    (apiService.resolveMcpConfirmation as any).mockResolvedValue(false);
    const onResolved = vi.fn();
    render(<ConfirmationCard pending={_basePending} onResolved={onResolved} />);
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(screen.getByText(/already expired/i)).toBeInTheDocument();
      expect(onResolved).toHaveBeenCalledWith('trace-123', true);
    });
  });

  it('surfaces network errors without unmounting', async () => {
    (apiService.resolveMcpConfirmation as any).mockRejectedValue(new Error('boom'));
    const onResolved = vi.fn();
    render(<ConfirmationCard pending={_basePending} onResolved={onResolved} />);
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => {
      expect(screen.getByText(/boom/i)).toBeInTheDocument();
      expect(onResolved).not.toHaveBeenCalled();
    });
  });
});

describe('useToolTrace', () => {
  it('collapses tool_call + tool_result into one row', () => {
    const { result } = renderHook(() => useToolTrace());
    act(() => {
      result.current.ingest({
        type: 'tool_call',
        trace_id: 't1',
        turn_id: 'turn-1',
        server_id: 'mpc_public',
        tool: 'search_mpc_items',
        args: { collection: 'sentinel-2-l2a' },
        tier: 'read',
        started_at: 0,
      } as any);
    });
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].status).toBe('pending');
    act(() => {
      result.current.ingest({
        type: 'tool_result',
        trace_id: 't1',
        turn_id: 'turn-1',
        server_id: 'mpc_public',
        tool: 'search_mpc_items',
        args: { collection: 'sentinel-2-l2a' },
        tier: 'read',
        started_at: 0,
        finished_at: 1,
        latency_ms: 123,
        ok: true,
        response_summary: '12 features',
      } as any);
    });
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].status).toBe('ok');
    expect(result.current.rows[0].latencyMs).toBe(123);
    expect(result.current.counts.read).toBe(1);
  });

  it('marks denied rows when error == denied_by_user', () => {
    const { result } = renderHook(() => useToolTrace());
    act(() => {
      result.current.ingest({
        type: 'tool_result',
        trace_id: 't2',
        turn_id: 'turn-1',
        server_id: 'mpc_pro',
        tool: 'delete_personal_collection',
        args: {},
        tier: 'destructive',
        started_at: 0,
        finished_at: 1,
        latency_ms: 0,
        ok: false,
        error: 'denied_by_user',
      } as any);
    });
    expect(result.current.rows[0].status).toBe('denied');
    expect(result.current.counts.error).toBe(1);
    expect(result.current.counts.destructive).toBe(1);
  });

  it('clear() resets state', () => {
    const { result } = renderHook(() => useToolTrace());
    act(() => {
      result.current.ingest({
        type: 'tool_call', trace_id: 't3', turn_id: 'x', server_id: 's', tool: 'list_mpc_stac_collections',
        args: {}, tier: 'read', started_at: 0,
      } as any);
    });
    expect(result.current.rows).toHaveLength(1);
    act(() => result.current.clear());
    expect(result.current.rows).toHaveLength(0);
    expect(result.current.counts.total).toBe(0);
  });
});
