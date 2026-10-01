package com.multify.autotrader.ui
import androidx.lifecycle.*
import com.multify.autotrader.AppContainer
import com.multify.autotrader.data.local.CapturedEventEntity
import com.multify.autotrader.data.repository.AppSettings
import com.multify.autotrader.domain.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class OverviewState(val loading:Boolean=true,val health:EngineHealth=EngineHealth(),val summary:DashboardSummary=DashboardSummary(),val positions:List<PositionSnapshot> = emptyList(),val events:List<CapturedEventEntity> = emptyList(),val pending:Int=0,val error:String?=null)
class OverviewVm(private val c:AppContainer):ViewModel(){
 private val remote=MutableStateFlow(OverviewState())
 val state=combine(remote,c.eventRepository.observeRecent(10),c.eventRepository.observePendingCount()){s,e,p->s.copy(events=e,pending=p)}.stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),OverviewState())
 init{refresh()}
 fun refresh()=viewModelScope.launch{remote.update{it.copy(loading=true,error=null)};runCatching{val h=c.engineRepository.health();val has=c.engineRepository.hasSecret();val d=if(has)c.engineRepository.dashboard() else null;val ps=if(has)c.engineRepository.positions() else emptyList();Triple(h,d,ps)}.onSuccess{(h,d,ps)->remote.value=OverviewState(false,EngineHealth(h.ok,h.tradingMode?:"unknown",h.brokerConfigured,h.scope?:"NSE CASH MIS",h.sessionState?:"UNKNOWN",h.killSwitch),DashboardSummary(d?.realisedPnl?:0.0,d?.unrealisedPnl?:0.0,d?.trades?:0,d?.wins?:0,d?.losses?:0,d?.openPositions?:ps.count{it.quantity!=0},d?.dailyProfitLock?:5000.0,d?.dailyLossLimit?:2000.0),ps.map{PositionSnapshot(it.symbol,it.quantity,it.averagePrice,it.ltp,it.unrealisedPnl,it.realisedPnl)},error=if(!c.engineRepository.hasSecret())"Configure the device secret to load protected data." else null)}.onFailure{e->remote.update{it.copy(loading=false,error=e.message)}}}
 fun kill(v:Boolean)=viewModelScope.launch{runCatching{c.engineRepository.setKillSwitch(v)};refresh()}
}
class SignalsVm(c:AppContainer):ViewModel(){val events=c.eventRepository.observeRecent(200).stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())}
class PositionsVm(private val c:AppContainer):ViewModel(){private val _s=MutableStateFlow<List<PositionSnapshot>>(emptyList());val positions=_s.asStateFlow();val error=MutableStateFlow<String?>(null);init{refresh()};fun refresh()=viewModelScope.launch{runCatching{c.engineRepository.positions()}.onSuccess{_s.value=it.map{x->PositionSnapshot(x.symbol,x.quantity,x.averagePrice,x.ltp,x.unrealisedPnl,x.realisedPnl)};error.value=null}.onFailure{error.value=it.message}}}
data class SettingsState(val settings:AppSettings=AppSettings(),val hasSecret:Boolean=false,val message:String?=null)
class SettingsVm(private val c:AppContainer):ViewModel(){private val temp=MutableStateFlow(SettingsState(hasSecret=c.secretStore.hasDeviceSecret()));val state=combine(c.settingsRepository.settings,temp){s,t->t.copy(settings=s,hasSecret=c.secretStore.hasDeviceSecret())}.stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),SettingsState());fun save(url:String,filter:String,secret:String?)=viewModelScope.launch{runCatching{c.settingsRepository.updateBackendUrl(url);c.settingsRepository.updatePackageFilter(filter);if(secret!=null)c.secretStore.putDeviceSecret(secret)}.onSuccess{temp.value=temp.value.copy(hasSecret=c.secretStore.hasDeviceSecret(),message="Settings saved")}.onFailure{temp.value=temp.value.copy(message=it.message)}};fun forwarding(v:Boolean)=viewModelScope.launch{c.settingsRepository.setForwardingEnabled(v)}}
class AnalyticsVm(c:AppContainer):ViewModel(){val events=c.eventRepository.observeRecent(500).stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())}
class VmFactory(private val c:AppContainer):ViewModelProvider.Factory{@Suppress("UNCHECKED_CAST") override fun<T:ViewModel>create(k:Class<T>):T=when{ k.isAssignableFrom(OverviewVm::class.java)->OverviewVm(c) as T;k.isAssignableFrom(SignalsVm::class.java)->SignalsVm(c) as T;k.isAssignableFrom(PositionsVm::class.java)->PositionsVm(c) as T;k.isAssignableFrom(SettingsVm::class.java)->SettingsVm(c) as T;k.isAssignableFrom(AnalyticsVm::class.java)->AnalyticsVm(c) as T;else->error("Unknown ViewModel")}}
