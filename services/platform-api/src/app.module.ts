import {Module} from '@nestjs/common';
import {CoreModule} from './core.module';
import {DomainsModule} from './domains.module';
import {MetricsModule} from './metrics.module';
import {ContractsModule} from './contracts/contracts.module';
import {JobEventsModule} from './jobs/job-events.module';
import {TerritorialModule} from './territorial/territorial.module';
import {Property360Module} from './property360/property360.module';
import {ReportModule} from './report/report.module';
import {RuralModule} from './rural/rural.module';
import {CondoModule} from './condo/condo.module';
import {SolarModule} from './solar/solar.module';
import {MunicipalityModule} from './municipality/municipality.module';
import {PrivacyModule} from './privacy/privacy.module';
import {EntitlementSyncModule} from './entitlements/entitlement-sync.module';

@Module({imports:[CoreModule,TerritorialModule,Property360Module,ReportModule,RuralModule,CondoModule,SolarModule,MunicipalityModule,PrivacyModule,EntitlementSyncModule,DomainsModule,MetricsModule,ContractsModule,JobEventsModule]})
export class AppModule{}
