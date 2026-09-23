package com.suhas.globaledgeai.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.suhas.globaledgeai.GlobalEdgeApplication

class LearningWorker(appContext:Context,params:WorkerParameters):CoroutineWorker(appContext,params){
    override suspend fun doWork():Result{
        val repo=(applicationContext as GlobalEdgeApplication).repository
        if(!repo.settings().learningEnabled)return Result.success()

        return try{
            repo.runAutonomousLearningPass()
            Result.success()
        }catch(t:Throwable){
            if(repo.isAuthenticationFailure(t)){
                repo.invalidateAccessToken()
                if(repo.ensureAutomationAuthentication()){
                    runCatching{repo.runAutonomousLearningPass()}.fold(
                        onSuccess={Result.success()},
                        onFailure={Result.retry()}
                    )
                }else Result.success()
            }else Result.retry()
        }
    }
}
