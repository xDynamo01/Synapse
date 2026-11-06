import type { CommandRequest } from '../generated/ts/synapse/foundation/v1/CommandRequest.js';
import type { SubscribeFrame } from '../generated/ts/synapse/foundation/v1/SubscribeFrame.js';
// These are compile-time assertions against freshly generated contract types.
// @ts-expect-error command_id is an opaque string, not a number
const numericId: CommandRequest = { command_id: 42 };
// @ts-expect-error credentials are not part of a domain command
const leakedToken: CommandRequest = { token: 'forbidden' };
// @ts-expect-error event cursor must retain exact decimal-string identity
const numericCursor: SubscribeFrame = { after_event_id: 9007199254740993 };
void [numericId, leakedToken, numericCursor];
