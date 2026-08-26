import {Module} from '@nestjs/common';
import {EntitlementSyncController} from './entitlement-sync.controller';

@Module({controllers:[EntitlementSyncController]})
export class EntitlementSyncModule{}
