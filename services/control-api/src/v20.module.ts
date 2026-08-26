import {Module} from '@nestjs/common';
import {AppModule} from './app.module';
import {ControlV20AdminController,ControlV20InternalController,ControlV20PublicController} from './v20-admin.controller';
import {BillingEntitlementController} from './billing-entitlement.controller';

@Module({imports:[AppModule],controllers:[ControlV20AdminController,ControlV20InternalController,ControlV20PublicController,BillingEntitlementController]})
export class ControlV20Module{}
