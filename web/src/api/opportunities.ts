import { request } from './client';
import type { OpportunityPage, OpportunityRange } from './types';

export const readOpportunities = (range: OpportunityRange): Promise<OpportunityPage> =>
  request<OpportunityPage>(`/opportunities?range=${range}`);
