@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.suhas.globaledgeai.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun AppNavigation(vm:MainViewModel){
    val state by vm.state.collectAsStateWithLifecycle()
    var setupOpen by remember{ mutableStateOf(false) }
    var utilityPage by remember{ mutableStateOf("auth") }
    Scaffold(
        containerColor=MaterialTheme.colorScheme.background,
        topBar={
            TopAppBar(
                title={Text(if(setupOpen) "Setup" else "Global Quant Trader v2.2")},
                navigationIcon={if(setupOpen) IconButton(onClick={setupOpen=false}){Icon(Icons.Default.ArrowBack,"Back")}},
                actions={if(!setupOpen) IconButton(onClick={setupOpen=true}){Icon(Icons.Default.Settings,"Authentication and settings")}}
            )
        }
    ){padding->
        if(setupOpen) MoreScreen(state,vm,padding,utilityPage){utilityPage=it}
        else QuantV22Screen(state,vm,padding)
    }
}
